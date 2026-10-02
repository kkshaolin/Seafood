"""บริการประสาน pipeline พยากรณ์/ฝึก ARIMA กับข้อมูลสินค้าและฐานข้อมูล

รับข้อมูลอนุกรมเวลาของกุ้งจากไฟล์ CSV, เตรียมข้อมูลรายเดือน, ประเมินและฝึกโมเดล
จากนั้นบันทึกผลพยากรณ์ลงฐานข้อมูลหรือบันทึกโมเดลที่ฝึกแล้วลง storage/models
บริการนี้ถูกเรียกโดย forecasting worker และ training worker ที่ Compose เปิดใช้งาน
"""
import logging
import os

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from statsmodels.tsa.arima.model import ARIMAResults

from models.stock import InventorySummary, ForecastResult
from forecasting.schemas import ForecastRequest, ForecastResponse, ForecastDataPoint, ForecastMetrics
from inference_worker.forecast_model.preprocessing import prepare_time_series, chronological_split, PreprocessingError
from inference_worker.forecast_model.arima import train_arima, forecast_arima
from inference_worker.forecast_model.metrics import calculate_mae, calculate_rmse, calculate_mape
from inventory_data import get_local_arima_model_path, load_inventory_time_series

logger = logging.getLogger("forecasting_worker.service")

class ForecastingService:
    """รวมขั้นตอนอ่านข้อมูล เตรียมโมเดล และบันทึกผลผ่าน SQLAlchemy session"""

    def __init__(self, session: AsyncSession):
        """รับ session แบบ async ที่ worker เปิดไว้สำหรับหนึ่งงาน"""
        self.session = session

    async def get_inventory_data(self) -> pd.DataFrame:
        """Read inventory quantities from PostgreSQL, falling back to the configured CSV."""
        stmt = (
            select(InventorySummary.date, InventorySummary.total_boxes)
            .order_by(InventorySummary.date, InventorySummary.time)
        )
        result = await self.session.execute(stmt)
        rows = result.all()
        if rows:
            return pd.DataFrame(
                {
                    "recorded_at": [row.date for row in rows],
                    "quantity": [float(row.total_boxes) for row in rows],
                }
            )

        logger.warning("No inventory rows in PostgreSQL; using the inventory CSV fallback")
        try:
            return load_inventory_time_series()
        except (FileNotFoundError, ValueError) as exc:
            raise PreprocessingError(f"No usable inventory data is available: {exc}") from exc

    async def get_detected_stock_data(self) -> pd.DataFrame:
        """คืน DataFrame ว่างเป็น placeholder จนกว่าจะมีแหล่งข้อมูล CameraLog"""
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
        stock_df = await self.get_inventory_data()
        if stock_df.empty:
            raise PreprocessingError(f"Insufficient data: No stock records found for product '{req.product}'")
            
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
        
        # 2. Try to Load Pre-trained Model (.pkl)
        # Using a fixed path for simplicity or dynamic based on product
        model_path = get_local_arima_model_path(req.product)
        
        full_model = None
        model_uri = f"local://{model_path}"
        mae, rmse, mape = 0.0, 0.0, 0.0
        
        if os.path.exists(model_path):
            try:
                # Load pre-trained model
                loaded_model = ARIMAResults.load(model_path)
                
                # Apply new data to the pre-trained model to update its state
                # Note: statsmodels apply creates a new results object with the same parameters
                # Exogenous variables not handled in this basic apply for simplicity
                full_model = loaded_model.apply(monthly_df['quantity'])
                logger.info("Loaded and applied model from %s", model_path)
            except Exception as e:
                logger.warning("Failed to load/apply model from %s: %s", model_path, e)
                
        # 3. Fallback: Retrain if load failed
        if full_model is None:
            # Quick train/test for metrics
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
            except Exception as exc:
                logger.warning("Forecast metric evaluation failed: %s", exc)
                
            full_model = train_arima(monthly_df, 'quantity', exog_cols, req.p, req.d, req.q)
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
        
        # 5. Save ForecastResult to DB
        api_results = []
        for dt, pred, lower, upper in zip(future_dates, future_forecast, conf_int.iloc[:, 0], conf_int.iloc[:, 1]):
            fr = ForecastResult(
                product=req.product,
                forecast_date=dt.date(),
                predicted_value=float(pred),
                lower_bound=float(lower),
                upper_bound=float(upper),
                model_name="ARIMA_Inference",
                model_version=model_uri
            )
            self.session.add(fr)
            api_results.append(ForecastDataPoint(
                date=dt.date(),
                predicted_value=float(pred),
                lower_bound=float(lower),
                upper_bound=float(upper)
            ))
            
        await self.session.commit()
        
        metrics = ForecastMetrics(mae=mae, rmse=rmse, mape=mape)
        return ForecastResponse(
            product=req.product,
            model_name="ARIMA_Inference",
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

        stock_df = await self.get_inventory_data()
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
        mae, rmse, mape = 0.0, 0.0, 0.0
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
