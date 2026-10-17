"""บริการประสาน pipeline พยากรณ์/ฝึก ARIMA กับข้อมูลสินค้าและฐานข้อมูล

รับข้อมูลอนุกรมเวลาของกุ้งจากไฟล์ CSV, เตรียมข้อมูลรายเดือน, ประเมินและฝึกโมเดล
จากนั้นบันทึกผลพยากรณ์ลงฐานข้อมูลหรือบันทึกโมเดลที่ฝึกแล้วลง storage/models
บริการนี้ถูกเรียกโดย forecasting worker และ training worker ที่ Compose เปิดใช้งาน
"""
import logging
import os
from pathlib import Path
from typing import Optional

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from statsmodels.tsa.arima.model import ARIMAResults

from models.stock import MonthlyInventory, DailyInventory, ArimaForecast, SarimaxForecast, ForecastResult, BoxLog
from forecasting.schemas import ForecastRequest, ForecastResponse, ForecastDataPoint, ForecastMetrics
from inference_worker.forecast_model.preprocessing import prepare_time_series, chronological_split, PreprocessingError
from inference_worker.forecast_model.arima import (
    train_arima, forecast_arima, select_optimal_arima_order,
    train_sarimax, forecast_sarimax, select_optimal_sarimax_order,
    extract_sarimax_feature_importance,
)
from inference_worker.forecast_model.metrics import calculate_mae, calculate_rmse, calculate_mape
from inventory_data import get_local_arima_model_path, load_inventory_time_series
from data_worker.data_service import get_exogenous_matrix

logger = logging.getLogger("forecasting_worker.service")

class ForecastingService:
    """รวมขั้นตอนอ่านข้อมูล เตรียมโมเดล และบันทึกผลผ่าน SQLAlchemy session"""

    def __init__(self, session: AsyncSession):
        """รับ session แบบ async ที่ worker เปิดไว้สำหรับหนึ่งงาน"""
        self.session = session

    async def get_inventory_data(
        self,
        product: Optional[str] = None,
        model_type: Optional[str] = "total",
    ) -> pd.DataFrame:
        """Read inventory quantities from monthly_inventories or daily_inventories based on model_type."""
        from sqlalchemy import or_, func

        clean_p = product.replace("_", " ").strip() if product else ""

        # 1. Inbound or Outbound Dual-Model Queries from daily_inventories aggregated by month
        if model_type in ("inbound", "outbound"):
            col = DailyInventory.inbound_boxes if model_type == "inbound" else DailyInventory.outbound_boxes
            stmt_daily = (
                select(DailyInventory.time, col)
                .order_by(DailyInventory.time.asc())
            )
            if clean_p:
                stmt_daily = stmt_daily.where(
                    or_(
                        func.lower(DailyInventory.product) == clean_p.lower(),
                        func.lower(DailyInventory.product).like(f"%{clean_p.lower()}%")
                    )
                )
            result_daily = await self.session.execute(stmt_daily)
            rows_daily = result_daily.all()
            if rows_daily:
                df_daily = pd.DataFrame({
                    "recorded_at": [row[0] for row in rows_daily],
                    "quantity": [float(row[1]) for row in rows_daily],
                })
                df_daily["recorded_at"] = pd.to_datetime(df_daily["recorded_at"], utc=True)
                df_monthly = df_daily.set_index("recorded_at").resample("MS")["quantity"].sum().reset_index()
                if not df_monthly.empty and df_monthly["quantity"].sum() > 0:
                    return df_monthly

        # 2. Standard Total Inventory Queries from monthly_inventories
        if clean_p:
            stmt = (
                select(MonthlyInventory.time, MonthlyInventory.total_boxes)
                .where(
                    or_(
                        func.lower(MonthlyInventory.product) == clean_p.lower(),
                        func.lower(MonthlyInventory.product).like(f"%{clean_p.lower()}%")
                    )
                )
                .order_by(MonthlyInventory.time.asc())
            )
            result = await self.session.execute(stmt)
            rows = result.all()
            if rows:
                return pd.DataFrame(
                    {
                        "recorded_at": [row.time for row in rows],
                        "quantity": [float(row.total_boxes) for row in rows],
                    }
                )

            # If alias is a known seafood product variant, map to main inventory records
            if clean_p.lower() in ("frozen seafood", "frozen shrimp", "premium white shrimp", "seafood", "shrimp"):
                stmt_all = select(MonthlyInventory.time, MonthlyInventory.total_boxes).order_by(MonthlyInventory.time.asc())
                result_all = await self.session.execute(stmt_all)
                rows_all = result_all.all()
                if rows_all:
                    return pd.DataFrame(
                        {
                            "recorded_at": [row.time for row in rows_all],
                            "quantity": [float(row.total_boxes) for row in rows_all],
                        }
                    )

            # Product is unknown: return empty DataFrame so caller raises PreprocessingError
            return pd.DataFrame(columns=["recorded_at", "quantity"])

        # No product specified: return all monthly inventory rows
        stmt_default = select(MonthlyInventory.time, MonthlyInventory.total_boxes).order_by(MonthlyInventory.time.asc())
        res_default = await self.session.execute(stmt_default)
        rows_def = res_default.all()
        if rows_def:
            return pd.DataFrame(
                {
                    "recorded_at": [row.time for row in rows_def],
                    "quantity": [float(row.total_boxes) for row in rows_def],
                }
            )

        logger.warning("No rows matching in monthly_inventories; falling back to CSV")
        try:
            return load_inventory_time_series()
        except (FileNotFoundError, ValueError) as exc:
            raise PreprocessingError(f"No usable inventory data is available: {exc}") from exc

    async def get_detected_stock_data(self) -> pd.DataFrame:
        """Query box_logs as exogenous camera detection data if available."""
        stmt = (
            select(BoxLog.time, BoxLog.total_boxes)
            .order_by(BoxLog.time.asc())
        )
        result = await self.session.execute(stmt)
        rows = result.all()
        if rows:
            return pd.DataFrame(
                {
                    "recorded_at": [row.time for row in rows],
                    "detected_stock": [float(row.total_boxes) for row in rows],
                }
            )
        return pd.DataFrame(columns=['recorded_at', 'detected_stock'])

    async def run_forecast(self, req: ForecastRequest) -> ForecastResponse:
        """สร้าง forecast ตามคำขอด้วย SARIMAX พร้อมตัวแปรภายนอกและการจำลอง What-If

        รองรับ Dual-Model (inbound, outbound, total), ประเมินตัวชี้วัด holdout,
        พยากรณ์ตาม horizon และบันทึกลงตาราง sarimax_forecasts และตารางดั้งเดิม
        """
        import json
        if req.warehouse:
            raise PreprocessingError(
                "Inventory summary data has no warehouse column; warehouse filtering is unsupported"
            )

        model_type = req.model_type or "total"

        # 1. Load Monthly Data from DB (based on model_type: inbound, outbound, total)
        stock_df = await self.get_inventory_data(req.product, model_type=model_type)
        if stock_df.empty:
            raise PreprocessingError(f"Insufficient data: No stock records found for product '{req.product}'")
        stock_df['recorded_at'] = pd.to_datetime(stock_df['recorded_at'], utc=True)
        monthly_df = prepare_time_series(stock_df, target_col='quantity', date_col='recorded_at')

        # 2. Exogenous Data Integration (Weather, Forex, Regulations)
        exog_cols = []
        future_exog_full = None
        feature_importance = []

        start_date = monthly_df.index[0].date()
        future_dates = pd.date_range(start=monthly_df.index[-1], periods=req.forecast_horizon + 1, freq='MS')[1:]
        future_end_date = future_dates[-1].date()

        if req.use_exog:
            try:
                exog_matrix = await get_exogenous_matrix(start_date, future_end_date, freq='MS')
                if not exog_matrix.empty:
                    # Select features according to dual-model domain role
                    if model_type == "inbound":
                        candidate_cols = ["is_storm", "is_fishing_ban", "lunar_phase", "wind_speed_max_kmh"]
                    elif model_type == "outbound":
                        candidate_cols = ["usd_thb", "brent_crude_usd", "is_christmas_newyear", "is_chinese_new_year"]
                    else:
                        candidate_cols = ["is_storm", "usd_thb", "is_fishing_ban", "lunar_phase"]

                    exog_cols = [c for c in candidate_cols if c in exog_matrix.columns]
                    if exog_cols:
                        # Align historical exog with monthly_df
                        aligned_exog = exog_matrix[exog_cols].reindex(monthly_df.index).ffill().bfill().fillna(0.0)
                        for col in exog_cols:
                            monthly_df[col] = aligned_exog[col]

                        # Prepare future exog slice with optional shocks
                        future_idx = pd.to_datetime(future_dates)
                        future_slice = exog_matrix[exog_cols].reindex(future_idx).ffill().bfill().fillna(0.0).copy()

                        # Apply What-If Shocks if requested
                        if req.storm_shock_days and req.storm_shock_days > 0 and "is_storm" in future_slice.columns:
                            future_slice.iloc[0, future_slice.columns.get_loc("is_storm")] += float(req.storm_shock_days)
                        if req.fx_shock_pct and req.fx_shock_pct != 0.0 and "usd_thb" in future_slice.columns:
                            future_slice["usd_thb"] = future_slice["usd_thb"] * (1.0 + float(req.fx_shock_pct) / 100.0)

                        future_exog_full = future_slice
                        logger.info("Using exogenous variables %s for %s SARIMAX", exog_cols, model_type)
            except Exception as exog_err:
                logger.warning("Could not merge exogenous data: %s. Continuing with pure time series.", exog_err)
                exog_cols = []

        # 3. Model Order Selection & Training
        use_p, use_d, use_q = req.p, req.d, req.q
        use_P, use_D, use_Q, use_s = req.P or 0, req.D or 0, req.Q or 0, req.s or 12

        # Auto-detect optimal order via AIC if using default orders
        if (req.p == 1 and req.d == 1 and req.q == 1 and (req.P == 0 or req.P is None)):
            try:
                logger.info("Auto-detecting optimal SARIMAX order...")
                (opt_p, opt_d, opt_q), (opt_P, opt_D, opt_Q, opt_s) = select_optimal_sarimax_order(
                    monthly_df, 'quantity', exog_cols, seasonal_period=12
                )
                use_p, use_d, use_q = opt_p, opt_d, opt_q
                use_P, use_D, use_Q, use_s = opt_P, opt_D, opt_Q, opt_s
                logger.info("Selected optimal SARIMAX: (%d,%d,%d)x(%d,%d,%d,%d)", use_p, use_d, use_q, use_P, use_D, use_Q, use_s)
            except Exception as opt_err:
                logger.warning("Auto order selection fallback failed: %s", opt_err)

        actual_order = (use_p, use_d, use_q)
        actual_seasonal = (use_P, use_D, use_Q, use_s)

        # 4. Chronological holdout evaluation for honest metrics
        mae, rmse, mape = None, None, None
        try:
            if len(monthly_df) >= 8:
                train_df, test_df = chronological_split(monthly_df, train_ratio=0.8)
                eval_model = train_sarimax(
                    train_df, 'quantity', exog_cols,
                    p=use_p, d=use_d, q=use_q,
                    P=use_P, D=use_D, Q=use_Q, s=use_s
                )
                test_exog = test_df[exog_cols] if exog_cols else None
                test_forecast, _ = forecast_sarimax(eval_model, steps=len(test_df), future_exog=test_exog)

                y_true = test_df['quantity'].values
                y_pred = test_forecast.values
                mae = calculate_mae(y_true, y_pred)
                rmse = calculate_rmse(y_true, y_pred)
                mape = calculate_mape(y_true, y_pred)
        except Exception as exc:
            logger.warning("Forecast metric holdout evaluation failed: %s", exc)

        # 5. Full Model Fitting
        full_model = train_sarimax(
            monthly_df, 'quantity', exog_cols,
            p=use_p, d=use_d, q=use_q,
            P=use_P, D=use_D, Q=use_Q, s=use_s
        )
        model_uri = f"sarimax_{req.product}_{model_type}"

        # Extract Feature Importance (Exogenous Coefficients)
        if exog_cols:
            feature_importance = extract_sarimax_feature_importance(full_model, exog_cols)

        # 6. Forecast Horizon
        future_forecast, conf_int = forecast_sarimax(full_model, steps=req.forecast_horizon, future_exog=future_exog_full)

        # 7. Persist to Database (SarimaxForecast + ArimaForecast + ForecastResult)
        model_order_str = f"SARIMAX({actual_order[0]},{actual_order[1]},{actual_order[2]})({actual_seasonal[0]},{actual_seasonal[1]},{actual_seasonal[2]},{actual_seasonal[3]})"
        api_results = []
        total_pred_boxes = 0

        for dt, pred, lower, upper in zip(future_dates, future_forecast, conf_int.iloc[:, 0], conf_int.iloc[:, 1]):
            pred_int = max(0, int(round(float(pred))))
            lower_int = max(0, int(round(float(lower))))
            upper_int = max(0, int(round(float(upper))))
            total_pred_boxes += pred_int

            # Save to new sarimax_forecasts table
            sf = SarimaxForecast(
                time=dt.date(),
                product=req.product,
                forecast_type=model_type,
                predicted_value=float(pred_int),
                lower_bound=float(lower_int),
                upper_bound=float(upper_int),
                model_order=model_order_str,
                feature_importance=json.dumps(feature_importance),
            )
            self.session.add(sf)

            # Save to legacy arima_forecasts table for backward compatibility
            af = ArimaForecast(
                time=dt.date(),
                product=req.product,
                total_boxes=float(pred_int),
                lower_bound=float(lower_int),
                upper_bound=float(upper_int),
                model_order=model_order_str,
            )
            self.session.add(af)

            # Save to legacy forecast_results table
            fr = ForecastResult(
                product=req.product,
                forecast_date=dt.date(),
                predicted_value=float(pred_int),
                lower_bound=float(lower_int),
                upper_bound=float(upper_int),
                model_name=model_order_str,
                model_version=model_uri,
            )
            self.session.add(fr)

            api_results.append(ForecastDataPoint(
                date=dt.date(),
                predicted_value=pred_int,
                lower_bound=lower_int,
                upper_bound=upper_int,
            ))

        await self.session.commit()

        # 8. Financial Impact (Assumed standard 10 kg/carton @ 220 THB/kg = 2,200 THB/box)
        price_per_box_thb = 2200.0
        financial_impact = {
            "total_predicted_boxes": total_pred_boxes,
            "total_value_thb": round(total_pred_boxes * price_per_box_thb, 2),
            "estimated_holding_cost_monthly_thb": round(total_pred_boxes * 45.0, 2),  # ~45 THB/box electricity
            "price_per_kg_thb": 220.0,
        }

        dual_summary = {
            "model_type": model_type,
            "seasonal_period": use_s,
            "exogenous_features": exog_cols,
            "horizon_months": req.forecast_horizon,
        }

        metrics = ForecastMetrics(
            mae=mae, rmse=rmse, mape=mape,
            aic=float(full_model.aic) if hasattr(full_model, "aic") else None,
            bic=float(full_model.bic) if hasattr(full_model, "bic") else None,
        )

        return ForecastResponse(
            product=req.product,
            model_name=model_order_str,
            metrics=metrics,
            forecast=api_results,
            model_uri=model_uri,
            model_type=model_type,
            feature_importance=feature_importance,
            financial_impact=financial_impact,
            dual_summary=dual_summary,
        )

    async def run_training(self, req: ForecastRequest) -> ForecastResponse:
        """ฝึกโมเดลจากข้อมูลทั้งหมด บันทึกไฟล์โมเดล และคืนตัวชี้วัดจาก holdout

        คำนวณ MAE/RMSE/MAPE จากการแบ่งข้อมูลตามเวลาเมื่อทำได้ ก่อนฝึกโมเดลเต็มชุด
        และบันทึกผลลัพธ์ไว้ใต้ storage/models/time_serie
        """
        if req.warehouse:
            raise PreprocessingError(
                "Inventory summary data has no warehouse column; warehouse filtering is unsupported"
            )

        stock_df = await self.get_inventory_data(req.product)
        if stock_df.empty:
            raise PreprocessingError(f"Insufficient data for training: No stock records found for product '{req.product}'")
        stock_df['recorded_at'] = pd.to_datetime(stock_df['recorded_at'], utc=True)
        df = stock_df
        exog_cols = []
            
        monthly_df = prepare_time_series(df, target_col='quantity', date_col='recorded_at')
        
        # Train-test split for metrics
        mae, rmse, mape = None, None, None
        try:
            train_df, test_df = chronological_split(monthly_df, train_ratio=0.8)
            model = train_arima(train_df, 'quantity', exog_cols, req.p, req.d, req.q)
            future_exog = test_df[exog_cols] if exog_cols else None
            test_forecast, _ = forecast_arima(model, steps=len(test_df), future_exog=future_exog)
            
            y_true = test_df['quantity'].values
            y_pred = test_forecast.values
            mae = calculate_mae(y_true, y_pred)
            rmse = calculate_rmse(y_true, y_pred)
            mape = calculate_mape(y_true, y_pred)
        except Exception as e:
            print(f"Metrics calc failed during training: {e}")
            
        # Train full model
        full_model = train_arima(monthly_df, 'quantity', exog_cols, req.p, req.d, req.q)
        
        model_path = get_local_arima_model_path(req.product)
        model_path.parent.mkdir(parents=True, exist_ok=True)
        full_model.save(model_path)
        
        return ForecastResponse(
            product=req.product,
            model_name="ARIMA",
            metrics=ForecastMetrics(mae=mae, rmse=rmse, mape=mape),
            forecast=[],
            model_uri=f"local://{model_path}"
        )
