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
    forecast_horizon: int = Field(default=3, ge=1, le=60, description="Forecast steps in months (1..60)")
    # Optional filter for warehouse if needed
    warehouse: Optional[str] = None

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
    sampled_frames: Optional[Dict[str, str]] = None
    sampled_detections: Optional[Dict[str, int]] = None
    sampling_error: Optional[str] = None

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
