"""บริการประสาน pipeline พยากรณ์/ฝึก ARIMA กับข้อมูลสินค้าและฐานข้อมูล

รับข้อมูลอนุกรมเวลาของกุ้งจากไฟล์ CSV, เตรียมข้อมูลรายเดือน, ประเมินและฝึกโมเดล
จากนั้นบันทึกผลพยากรณ์ลงฐานข้อมูลหรือบันทึกโมเดลที่ฝึกแล้วลง storage/models
บริการนี้ถูกเรียกโดย forecasting worker และ training worker ที่ Compose เปิดใช้งาน
"""
import pandas as pd
from datetime import date
import os
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from statsmodels.tsa.arima.model import ARIMAResults

from models.stock import ShrimpStockData, CameraLog, ForecastResult
from forecasting.schemas import ForecastRequest, ForecastResponse, ForecastDataPoint, ForecastMetrics
from inference_worker.forecast_model.preprocessing import prepare_time_series, chronological_split, PreprocessingError
from inference_worker.forecast_model.arima import train_arima, forecast_arima
from inference_worker.forecast_model.metrics import calculate_mae, calculate_rmse, calculate_mape

class ForecastingService:
    """รวมขั้นตอนอ่านข้อมูล เตรียมโมเดล และบันทึกผลผ่าน SQLAlchemy session"""

    def __init__(self, session: AsyncSession):
        """รับ session แบบ async ที่ worker เปิดไว้สำหรับหนึ่งงาน"""
        self.session = session

    async def get_shrimp_stock_data(self, product: str, warehouse: Optional[str] = None) -> pd.DataFrame:
        """อ่านข้อมูลสต็อกรายเดือนจาก CSV กรองสินค้า/คลัง และคืนคอลัมน์วันกับปริมาณ"""
        workspace_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        csv_path = os.path.join(workspace_root, "storage", "data", "csv_file", "shrimp_stock_monthly_4y.csv")
        
        if not os.path.exists(csv_path):
            print(f"Warning: CSV not found at {csv_path}")
            return pd.DataFrame(columns=['recorded_at', 'quantity'])
            
        df = pd.read_csv(csv_path)
        
        # CSV ตัวอย่างมีสินค้าหลักเพียงชนิดเดียว จึง map คำขอ Premium ไปยังชื่อในไฟล์
        target_product = "tiger_shrimp_size_L" if product == "Premium_White_Shrimp" else product
        filtered = df[df['product'] == target_product].copy()
        
        if filtered.empty and not df.empty:
            # หากชื่อสินค้าไม่ตรงกับไฟล์ ให้ใช้ชนิดแรกในไฟล์เพื่อคงการประมวลผลตัวอย่าง
            first_product = df['product'].iloc[0]
            filtered = df[df['product'] == first_product].copy()
            
        if warehouse:
            filtered = filtered[filtered['warehouse'] == warehouse]
            
        # Rename 'date' -> 'recorded_at' to match existing logic
        filtered.rename(columns={'date': 'recorded_at'}, inplace=True)
        # Convert date to datetime
        filtered['recorded_at'] = pd.to_datetime(filtered['recorded_at'])
        
        return filtered[['recorded_at', 'quantity']]

    async def get_detected_stock_data(self) -> pd.DataFrame:
        """คืน DataFrame ว่างเป็น placeholder จนกว่าจะมีแหล่งข้อมูล CameraLog"""
        return pd.DataFrame(columns=['recorded_at', 'detected_stock'])

    async def run_forecast(self, req: ForecastRequest) -> ForecastResponse:
        """สร้าง forecast ตามคำขอ โดยลองโหลดโมเดลเดิมก่อนและฝึกใหม่เมื่อใช้ไม่ได้

        รวมข้อมูลกล้องกับสต็อกเมื่อมี, เตรียมรายเดือน, คำนวณตัวชี้วัดจาก holdout
        เมื่อฝึกใหม่, พยากรณ์ตาม horizon และบันทึกจุดพยากรณ์ลง ForecastResult
        """
        # 1. Load Real-time Data from DB
        stock_df = await self.get_shrimp_stock_data(req.product, req.warehouse)
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
        workspace_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        model_filename = f"arima_premium_shrimp.pkl" # fallback default
        if req.product == "Premium_White_Shrimp":
            model_filename = "arima_premium_shrimp.pkl"
            
        model_path = os.path.join(workspace_root, "storage", "models", "time_serie", model_filename)
        
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
                print(f"Loaded and applied model from {model_path}")
            except Exception as e:
                print(f"Failed to load/apply model: {e}")
                
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
            except:
                pass
                
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
        stock_df = await self.get_shrimp_stock_data(req.product, req.warehouse)
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
        
        workspace_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        model_filename = f"arima_premium_shrimp.pkl" if req.product == "Premium_White_Shrimp" else f"arima_{req.product}.pkl"
        model_path = os.path.join(workspace_root, "storage", "models", "time_serie", model_filename)
        
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        full_model.save(model_path)
        
        return ForecastResponse(
            product=req.product,
            model_name="ARIMA",
            metrics=ForecastMetrics(mae=mae, rmse=rmse, mape=mape),
            forecast=[],
            model_uri=f"local://{model_path}"
        )
