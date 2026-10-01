"""Schema ของ response model สำหรับ stock API.

ใช้ Pydantic เป็น contract ระหว่าง FastAPI กับ frontend เพื่อให้ payload ที่ส่งกลับมีรูปแบบคงที่
และพร้อมใช้สำหรับ validation / serialization.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class StockUploadResponse(BaseModel):
    message: str
    records_inserted: int


class StockRecordResponse(BaseModel):
    id: int
    recorded_at: datetime
    product: str
    quantity: float
    unit: str
    warehouse: Optional[str] = None
    source: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StockSummaryResponse(BaseModel):
    current_stock: float
    average_stock: float
    minimum_stock: float
    maximum_stock: float
    latest_record: Optional[datetime] = None
    number_of_records: int


class StockHistoryDataPoint(BaseModel):
    recorded_at: datetime
    product: str
    quantity: float


class StockHistoryResponse(BaseModel):
    data: list[StockHistoryDataPoint]


class ProductListResponse(BaseModel):
    products: list[str]
