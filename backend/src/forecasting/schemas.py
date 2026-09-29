from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict
from datetime import date

class ForecastRequest(BaseModel):
    product: str
    p: int = 1
    d: int = 1
    q: int = 1
    forecast_horizon: int = 3
    # Optional filter for warehouse if needed
    warehouse: Optional[str] = None

class ForecastDataPoint(BaseModel):
    date: date
    predicted_value: float
    lower_bound: Optional[float] = None
    upper_bound: Optional[float] = None

class ForecastMetrics(BaseModel):
    mae: float
    rmse: float
    mape: float

class ForecastResponse(BaseModel):
    product: str
    model_name: str
    metrics: ForecastMetrics
    forecast: List[ForecastDataPoint]
    model_uri: Optional[str] = None

class ForecastJobResponse(BaseModel):
    job_id: str
    status: str

class ForecastJobStatusResponse(BaseModel):
    status: str
    result: Optional[ForecastResponse] = None
    error: Optional[str] = None
