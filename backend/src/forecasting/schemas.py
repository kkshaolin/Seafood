"""Schema ของ payload และ response สำหรับ forecasting workflow.

เป้าหมายคือให้ request/response ของ queue job, latest forecast และ metric มีรูปแบบใกล้เคียงกัน
และสะดวกต่อการใช้กับ frontend หรือ worker process.
"""

from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Union
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


# ---------------------------------------------------------------------------
# YOLO Training Schemas
# ---------------------------------------------------------------------------

class YoloTrainRequest(BaseModel):
    """คำขอฝึกโมเดล YOLO ที่ส่งไปยัง training_queue"""
    dataset_name: str = "box_v1"
    """ชื่อ dataset ใน MinIO: bucket=datasets, key=yolo/<dataset_name>/<dataset_name>.zip"""
    class_names: Optional[List[str]] = None
    """รายชื่อ class เช่น ["box"]; ถ้า null จะใช้ default ["box"]"""
    epochs: int = 10
    imgsz: int = 640
    batch: int = 8
    patience: int = 5
    """จำนวน epoch ที่ยอมให้ val loss ไม่ดีขึ้นก่อน early stop"""


class TrainJobResponse(BaseModel):
    """Response หลังจาก enqueue training job"""
    job_id: str
    status: str
    model_type: str
