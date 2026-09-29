import pandas as pd
from datetime import date
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from models.stock import ShrimpStockData, CameraLog, ForecastResult
from forecasting.schemas import ForecastRequest, ForecastResponse, ForecastDataPoint, ForecastMetrics
from forecasting.preprocessing import prepare_time_series, chronological_split, PreprocessingError
from forecasting.arimax import train_arimax, forecast_arimax
from forecasting.metrics import calculate_mae, calculate_rmse, calculate_mape


class ForecastingService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_shrimp_stock_data(self, product: str, warehouse: Optional[str] = None) -> pd.DataFrame:
        stmt = select(ShrimpStockData.recorded_at, ShrimpStockData.quantity).where(
            ShrimpStockData.product == product
        )
        if warehouse:
            stmt = stmt.where(ShrimpStockData.warehouse == warehouse)
            
        result = await self.session.execute(stmt)
        rows = result.fetchall()
        
        if not rows:
            return pd.DataFrame()
            
        df = pd.DataFrame(rows, columns=['recorded_at', 'quantity'])
        return df

    async def get_detected_stock_data(self) -> pd.DataFrame:
        # Load exogenous variable: detected_stock from camera logs
        stmt = select(CameraLog.captured_at, CameraLog.detected_count).where(
            CameraLog.processing_status == "processed"
        )
        result = await self.session.execute(stmt)
        rows = result.fetchall()
        
        if not rows:
            return pd.DataFrame()
            
        df = pd.DataFrame(rows, columns=['recorded_at', 'detected_stock'])
        return df

    async def run_forecast(self, req: ForecastRequest) -> ForecastResponse:
        # 1. Load Data
        stock_df = await self.get_shrimp_stock_data(req.product, req.warehouse)
        if stock_df.empty:
            raise PreprocessingError(f"Insufficient data: No stock records found for product '{req.product}'")
            
        camera_df = await self.get_detected_stock_data()
        
        # 2. Merge Data
        if not camera_df.empty:
            # We must group both by month to merge properly. We'll do it by merging DataFrames first
            df = pd.merge(stock_df, camera_df, on='recorded_at', how='outer')
            # Fill NaNs in quantity with 0
            df['quantity'] = df['quantity'].fillna(0.0)
            df['detected_stock'] = df['detected_stock'].fillna(0)
            exog_cols = ['detected_stock']
        else:
            df = stock_df
            exog_cols = []
            
        # 3. Preprocess
        monthly_df = prepare_time_series(df, target_col='quantity', date_col='recorded_at')
        
        # 4. Train/Test Split (80/20) for Metrics
        train_df, test_df = chronological_split(monthly_df, train_ratio=0.8)
        
        # 5. Train ARIMAX on train set
        try:
            model = train_arimax(train_df, 'quantity', exog_cols, req.p, req.d, req.q)
        except Exception as e:
            raise PreprocessingError(f"Failed to train ARIMAX model: {str(e)}")
            
        # 6. Forecast on test set for Metrics
        # For test forecasting, we need future_exog which is the exogenous variables from test_df
        future_exog = test_df[exog_cols] if exog_cols else None
        test_forecast, _ = forecast_arimax(model, steps=len(test_df), future_exog=future_exog)
        
        # 7. Metrics
        y_true = test_df['quantity'].values
        y_pred = test_forecast.values
        mae = calculate_mae(y_true, y_pred)
        rmse = calculate_rmse(y_true, y_pred)
        mape = calculate_mape(y_true, y_pred)
        metrics = ForecastMetrics(mae=mae, rmse=rmse, mape=mape)
        
        # 8. Retrain on FULL dataset for actual future forecast
        full_model = train_arimax(monthly_df, 'quantity', exog_cols, req.p, req.d, req.q)
        
        # Prepare future exogenous variables (e.g. naive approach: last known value repeated)
        if exog_cols:
            last_exog = monthly_df[exog_cols].iloc[-1]
            future_exog_full = pd.DataFrame([last_exog]*req.forecast_horizon, index=range(req.forecast_horizon))
        else:
            future_exog_full = None
            
        future_forecast, conf_int = forecast_arimax(full_model, steps=req.forecast_horizon, future_exog=future_exog_full)
        
        # Extract dates for future forecast
        last_date = monthly_df.index[-1]
        future_dates = pd.date_range(start=last_date, periods=req.forecast_horizon + 1, freq='MS')[1:]
        
        # 9. Save ForecastResult to DB
        db_results = []
        api_results = []
        for dt, pred, lower, upper in zip(future_dates, future_forecast, conf_int.iloc[:, 0], conf_int.iloc[:, 1]):
            # Save to DB
            fr = ForecastResult(
                product=req.product,
                forecast_date=dt.date(),
                predicted_value=float(pred),
                lower_bound=float(lower),
                upper_bound=float(upper),
                model_name="ARIMAX",
                model_version=f"p={req.p},d={req.d},q={req.q}"
            )
            self.session.add(fr)
            
            # Save for API Response
            api_results.append(ForecastDataPoint(
                date=dt.date(),
                predicted_value=float(pred),
                lower_bound=float(lower),
                upper_bound=float(upper)
            ))
            
        await self.session.commit()
        
        # MLflow Tracking
        import mlflow
        import os
        MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        mlflow.set_experiment(f"forecast_{req.product}")
        
        model_uri = None
        
        with mlflow.start_run() as run:
            # Log params
            mlflow.log_params({
                "product": req.product,
                "p": req.p,
                "d": req.d,
                "q": req.q,
                "forecast_horizon": req.horizon if hasattr(req, 'horizon') else req.forecast_horizon,
                "target": "quantity",
                "exogenous_variables": ",".join(exog_cols) if exog_cols else "none",
                "training_period_start": str(monthly_df.index[0].date()),
                "training_period_end": str(monthly_df.index[-1].date()),
                "total_records": len(monthly_df)
            })
            
            # Log metrics
            mlflow.log_metrics({
                "mae": mae,
                "rmse": rmse,
                "mape": mape
            })
            
            # Log Model using mlflow.statsmodels
            # (Note: since statsmodels ARIMA is natively supported, we use it)
            try:
                import mlflow.statsmodels
                model_info = mlflow.statsmodels.log_model(
                    statsmodels_model=full_model,
                    artifact_path="model"
                )
                model_uri = model_info.model_uri
            except ImportError:
                # If mlflow doesn't support statsmodels natively in this version
                pass
        
        return ForecastResponse(
            product=req.product,
            model_name="ARIMAX",
            metrics=metrics,
            forecast=api_results,
            model_uri=model_uri
        )
