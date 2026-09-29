import datetime
import random
from fastapi import APIRouter
from statsmodels.tsa.arima.model import ARIMA
import pandas as pd

router = APIRouter(prefix="/api/inventory", tags=["inventory"])

@router.get("/mock-forecast")
def get_inventory_forecast():
    # 1. Generate 30 days of mock inventory data
    dates = pd.date_range(end=datetime.datetime.now(), periods=30, freq='D')
    
    # Random walk with some trend
    inventory_levels = [1000]
    for _ in range(29):
        change = random.uniform(-50, 60) # Slight upward trend
        inventory_levels.append(max(0, inventory_levels[-1] + change))
        
    df = pd.DataFrame({'date': dates, 'inventory': inventory_levels})
    df.set_index('date', inplace=True)
    
    # 2. Fit ARIMA model
    # For a simple random walk, ARIMA(1,1,1) is a decent starting point
    model = ARIMA(df['inventory'], order=(1, 1, 1))
    model_fit = model.fit()
    
    # 3. Forecast next 7 days
    forecast_steps = 7
    forecast = model_fit.forecast(steps=forecast_steps)
    forecast_dates = pd.date_range(start=dates[-1] + pd.Timedelta(days=1), periods=forecast_steps, freq='D')
    
    # 4. Prepare data for frontend
    historical_data = [
        {"date": date.strftime("%m-%d"), "actual": round(val, 2), "forecast": None}
        for date, val in zip(dates, inventory_levels)
    ]
    
    # Connect the last actual point to the forecast line for a smooth chart
    last_actual = historical_data[-1].copy()
    last_actual["forecast"] = last_actual["actual"]
    
    forecast_data = [
        {"date": date.strftime("%m-%d"), "actual": None, "forecast": round(val, 2)}
        for date, val in zip(forecast_dates, forecast)
    ]
    
    # Replace the last historical point with the connected point
    historical_data[-1] = last_actual
    
    # Return combined data
    return historical_data + forecast_data
