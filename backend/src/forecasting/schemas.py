"""Schema ของ payload และ response สำหรับ forecasting workflow.

เป้าหมายคือให้ request/response ของ queue job, latest forecast และ metric มีรูปแบบใกล้เคียงกัน
และสะดวกต่อการใช้กับ frontend หรือ worker process.
"""

from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Dict, Union, Any
from datetime import date

class ForecastRequest(BaseModel):
    product: str = Field(..., min_length=1, description="Product identifier (non-empty)")
    p: int = Field(default=1, ge=0, le=10, description="AR order (0..10)")
    d: int = Field(default=1, ge=0, le=5, description="Differencing order (0..5)")
    q: int = Field(default=1, ge=0, le=10, description="MA order (0..10)")
    P: Optional[int] = Field(default=0, ge=0, le=5, description="Seasonal AR order (0..5)")
    D: Optional[int] = Field(default=0, ge=0, le=3, description="Seasonal Differencing (0..3)")
    Q: Optional[int] = Field(default=0, ge=0, le=5, description="Seasonal MA order (0..5)")
    s: Optional[int] = Field(default=12, ge=0, le=52, description="Seasonal period (12 for monthly, 7 for daily)")
    forecast_horizon: int = Field(default=3, ge=1, le=60, description="Forecast steps in months (1..60)")
    model_type: Optional[str] = Field(default="total", description="'inbound', 'outbound', or 'total'")
    use_exog: Optional[bool] = Field(default=True, description="Whether to include external weather & forex indicators")
    storm_shock_days: Optional[int] = Field(default=0, ge=0, le=30, description="What-if simulation: extra storm days")
    fx_shock_pct: Optional[float] = Field(default=0.0, description="What-if simulation: FX percentage shift")
    # Optional filter for warehouse if needed
    warehouse: Optional[str] = None
    video_time: Optional[float] = None
    video_time_a: Optional[float] = None
    video_time_b: Optional[float] = None
    timestamp: Optional[float] = None

class ForecastDataPoint(BaseModel):
    date: date
    predicted_value: float
    lower_bound: Optional[float] = None
    upper_bound: Optional[float] = None

class ForecastMetrics(BaseModel):
    mae: Optional[float] = None
    rmse: Optional[float] = None
    mape: Optional[float] = None
    aic: Optional[float] = None
    bic: Optional[float] = None
    baselines: Optional[Dict[str, Any]] = None
    evaluation_notes: Optional[Dict[str, Any]] = None

class ForecastResponse(BaseModel):
    product: str
    model_name: str
    metrics: ForecastMetrics
    forecast: List[ForecastDataPoint]
    model_uri: Optional[str] = None
    model_type: Optional[str] = "total"
    feature_importance: Optional[List[Dict[str, Any]]] = None
    dual_summary: Optional[Dict[str, Any]] = None
    financial_impact: Optional[Dict[str, Any]] = None
    sampled_frames: Optional[Dict[str, str]] = None
    sampled_detections: Optional[Dict[str, int]] = None
    sampling_error: Optional[str] = None

class WhatIfSimulateRequest(BaseModel):
    product: str = Field(default="Frozen Shrimp")
    forecast_horizon: int = Field(default=3, ge=1, le=12)
    storm_days: int = Field(default=0, ge=0, le=14)
    fx_change_pct: float = Field(default=0.0)  # e.g. +5% or -5%
    fishing_ban_active: Optional[bool] = None
    price_per_kg_thb: float = Field(default=220.0)

class WhatIfSimulateResponse(BaseModel):
    baseline_forecast: List[ForecastDataPoint]
    simulated_forecast: List[ForecastDataPoint]
    delta_boxes: int
    delta_percentage: float
    financial_impact_thb: float
    recommendation: str
    feature_impacts: List[Dict[str, Any]]

class ForecastJobResponse(BaseModel):
    job_id: str
    status: str

class TrainingJobResult(BaseModel):
    """ผลลัพธ์จาก training job (ARIMA หรือ YOLO) ที่ worker คืนมา"""
    model_config = ConfigDict(extra="allow")  # รับ field เพิ่มเติมโดยไม่ error
    status: str
    model_type: Optional[str] = None
    job_id: Optional[str] = None
    product: Optional[str] = None
    dataset_name: Optional[str] = None
    model_uri: Optional[str] = None
    metrics: Optional[Dict] = None
    error: Optional[str] = None


class ForecastJobStatusResponse(BaseModel):
    status: str
    result: Optional[Union[TrainingJobResult, ForecastResponse]] = None
    error: Optional[str] = None
    sampled_frames: Optional[Dict[str, str]] = None
    sampled_detections: Optional[Dict[str, int]] = None
    sampling_error: Optional[str] = None


# ---------------------------------------------------------------------------
# YOLO Training Schemas
# ---------------------------------------------------------------------------

class YoloTrainRequest(BaseModel):
    """คำขอฝึกโมเดล YOLO ที่ส่งไปยัง training_queue"""
    dataset_name: str = Field(default="box_v1", min_length=1, description="Dataset name in MinIO")
    """ชื่อ dataset ใน MinIO: bucket=datasets, key=yolo/<dataset_name>/<dataset_name>.zip"""
    class_names: Optional[List[str]] = Field(default_factory=lambda: ["delivery_box"], description="รายชื่อ class เช่น ['delivery_box']")
    epochs: int = Field(default=10, ge=1, le=1000, description="Training epochs (1..1000)")
    imgsz: int = Field(default=640, ge=32, le=2048, description="Image size (32..2048)")
    batch: int = Field(default=8, ge=1, le=256, description="Batch size (1..256)")
    patience: int = Field(default=5, ge=1, le=100, description="Early stopping patience (1..100)")
    """จำนวน epoch ที่ยอมให้ val loss ไม่ดีขึ้นก่อน early stop"""


class TrainJobResponse(BaseModel):
    """Response หลังจาก enqueue training job"""
    job_id: str
    status: str
    model_type: str
