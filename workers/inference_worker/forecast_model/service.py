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

from models.stock import MonthlyInventory, ArimaForecast, ForecastResult, BoxLog
from forecasting.schemas import ForecastRequest, ForecastResponse, ForecastDataPoint, ForecastMetrics
from inference_worker.forecast_model.preprocessing import prepare_time_series, chronological_split, PreprocessingError
from inference_worker.forecast_model.arima import train_arima, forecast_arima, select_optimal_arima_order
from inference_worker.forecast_model.metrics import calculate_mae, calculate_rmse, calculate_mape
from inventory_data import get_local_arima_model_path, load_inventory_time_series

logger = logging.getLogger("forecasting_worker.service")

class ForecastingService:
    """รวมขั้นตอนอ่านข้อมูล เตรียมโมเดล และบันทึกผลผ่าน SQLAlchemy session"""

    def __init__(self, session: AsyncSession):
        """รับ session แบบ async ที่ worker เปิดไว้สำหรับหนึ่งงาน"""
        self.session = session

    async def get_inventory_data(self, product: Optional[str] = None) -> pd.DataFrame:
        """Read monthly inventory quantities from PostgreSQL monthly_inventories table filtered by product."""
        from sqlalchemy import or_, func

        clean_p = product.replace("_", " ").strip() if product else ""
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
        """สร้าง forecast ตามคำขอ โดยลองโหลดโมเดลเดิมก่อนและฝึกใหม่เมื่อใช้ไม่ได้

        รวมข้อมูลกล้องกับสต็อกเมื่อมี, เตรียมรายเดือน, คำนวณตัวชี้วัดจาก holdout
        เมื่อฝึกใหม่, พยากรณ์ตาม horizon และบันทึกจุดพยากรณ์ลง ForecastResult
        """
        if req.warehouse:
            raise PreprocessingError(
                "Inventory summary data has no warehouse column; warehouse filtering is unsupported"
            )

        # 1. Load Real-time Data from DB
        stock_df = await self.get_inventory_data(req.product)
        if stock_df.empty:
            raise PreprocessingError(f"Insufficient data: No stock records found for product '{req.product}'")
        stock_df['recorded_at'] = pd.to_datetime(stock_df['recorded_at'], utc=True)
            
        camera_df = await self.get_detected_stock_data()
        
        if not camera_df.empty:
            camera_df['recorded_at'] = pd.to_datetime(camera_df['recorded_at'], utc=True)
            df = pd.merge(stock_df, camera_df, on='recorded_at', how='outer')
            df['quantity'] = df['quantity'].fillna(0.0)
            df['detected_stock'] = df['detected_stock'].fillna(0)
            exog_cols = ['detected_stock']
        else:
            df = stock_df
            exog_cols = []
            
        monthly_df = prepare_time_series(df, target_col='quantity', date_col='recorded_at')
        
        # 2. Try to Load Pre-trained Model (.pkl)
        # Using a fixed path for simplicity or dynamic based on product
        model_path = get_local_arima_model_path(req.product)
        
        full_model = None
        model_uri = f"local://{model_path}"
        mae, rmse, mape = None, None, None
        actual_order = (req.p, req.d, req.q)
        
        if os.path.exists(model_path):
            try:
                # Load pre-trained model
                loaded_model = ARIMAResults.load(model_path)
                order_tuple = getattr(getattr(loaded_model, "model", None), "order", None)
                if order_tuple and len(order_tuple) == 3:
                    actual_order = order_tuple
                
                # Apply new data to the pre-trained model to update its state
                has_exog = hasattr(loaded_model.model, 'exog') and loaded_model.model.exog is not None
                exog_data = monthly_df[exog_cols] if (has_exog and exog_cols) else None
                full_model = loaded_model.apply(monthly_df['quantity'], exog=exog_data)
                logger.info("Loaded and applied model from %s with order ARIMA%s", model_path, actual_order)

                # Try loading saved metrics from accompanying JSON
                metrics_path = Path(model_path).with_suffix(".json")
                if metrics_path.exists():
                    try:
                        import json
                        m_data = json.loads(metrics_path.read_text(encoding="utf-8"))
                        mae = float(m_data["mae"]) if m_data.get("mae") is not None else None
                        rmse = float(m_data["rmse"]) if m_data.get("rmse") is not None else None
                        mape = float(m_data["mape"]) if m_data.get("mape") is not None else None
                        logger.info("Loaded metrics from %s: MAE=%s, RMSE=%s, MAPE=%s", metrics_path, mae, rmse, mape)
                    except Exception as err_m:
                        logger.warning("Could not read metrics from %s: %s", metrics_path, err_m)
            except Exception as e:
                logger.warning("Failed to load/apply model from %s: %s", model_path, e)
                
        # 3. Fallback: Retrain if load failed
        if full_model is None:
            # Auto-detect optimal order via ACF/PACF & AIC if using default (1,1,1)
            use_p, use_d, use_q = req.p, req.d, req.q
            if req.p == 1 and req.d == 1 and req.q == 1:
                try:
                    logger.info("Auto-detecting optimal order for fallback training via ACF/PACF & AIC...")
                    opt_p, opt_d, opt_q = select_optimal_arima_order(monthly_df, 'quantity', exog_cols)
                    use_p, use_d, use_q = opt_p, opt_d, opt_q
                    logger.info("Fallback training selected optimal order: ARIMA(%d,%d,%d)", use_p, use_d, use_q)
                except Exception as opt_err:
                    logger.warning("Auto order selection in fallback failed: %s", opt_err)
            actual_order = (use_p, use_d, use_q)

            # Quick train/test for metrics
            try:
                train_df, test_df = chronological_split(monthly_df, train_ratio=0.8)
                model = train_arima(train_df, 'quantity', exog_cols, use_p, use_d, use_q)
                future_exog = test_df[exog_cols] if exog_cols else None
                test_forecast, _ = forecast_arima(model, steps=len(test_df), future_exog=future_exog)
                
                y_true = test_df['quantity'].values
                y_pred = test_forecast.values
                mae = calculate_mae(y_true, y_pred)
                rmse = calculate_rmse(y_true, y_pred)
                mape = calculate_mape(y_true, y_pred)
            except Exception as exc:
                logger.warning("Forecast metric evaluation failed: %s", exc)
                
            full_model = train_arima(monthly_df, 'quantity', exog_cols, use_p, use_d, use_q)
            model_uri = "trained_from_scratch"
            
        # 4. Forecast Future (3 months or req.forecast_horizon)
        # Prepare future exogenous variables
        if exog_cols:
            last_exog = monthly_df[exog_cols].iloc[-1]
            future_exog_full = pd.DataFrame([last_exog]*req.forecast_horizon, index=range(req.forecast_horizon))
        else:
            future_exog_full = None
            
        future_forecast, conf_int = forecast_arima(full_model, steps=req.forecast_horizon, future_exog=future_exog_full)
        
        last_date = monthly_df.index[-1]
        future_dates = pd.date_range(start=last_date, periods=req.forecast_horizon + 1, freq='MS')[1:]
        
        # 5. Save ArimaForecast to DB
        model_order_str = f"ARIMA({actual_order[0]},{actual_order[1]},{actual_order[2]})"
        api_results = []
        for dt, pred, lower, upper in zip(future_dates, future_forecast, conf_int.iloc[:, 0], conf_int.iloc[:, 1]):
            pred_int = int(round(float(pred)))
            lower_int = max(0, int(round(float(lower))))
            upper_int = max(0, int(round(float(upper))))

            # 1. Save to new arima_forecasts table (integer box count)
            af = ArimaForecast(
                time=dt.date(),
                product=req.product,
                total_boxes=float(pred_int),
                lower_bound=float(lower_int),
                upper_bound=float(upper_int),
                model_order=model_order_str
            )
            self.session.add(af)

            # 2. Also save to old forecast_results table for backward compatibility
            fr = ForecastResult(
                product=req.product,
                forecast_date=dt.date(),
                predicted_value=float(pred_int),
                lower_bound=float(lower_int),
                upper_bound=float(upper_int),
                model_name=model_order_str,
                model_version=model_uri
            )
            self.session.add(fr)

            api_results.append(ForecastDataPoint(
                date=dt.date(),
                predicted_value=pred_int,
                lower_bound=lower_int,
                upper_bound=upper_int
            ))
            
        await self.session.commit()
        
        metrics = ForecastMetrics(mae=mae, rmse=rmse, mape=mape)
        return ForecastResponse(
            product=req.product,
            model_name=model_order_str,
            metrics=metrics,
            forecast=api_results,
            model_uri=model_uri
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
            
        camera_df = await self.get_detected_stock_data()
        
        if not camera_df.empty:
            df = pd.merge(stock_df, camera_df, on='recorded_at', how='outer')
            df['quantity'] = df['quantity'].fillna(0.0)
            df['detected_stock'] = df['detected_stock'].fillna(0)
            exog_cols = ['detected_stock']
        else:
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
