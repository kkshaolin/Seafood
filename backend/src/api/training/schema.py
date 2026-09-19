from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class TrainingRequest(BaseModel):
    """Schema สำหรับรับ request เทรนโมเดล"""
    dataset_name: str = Field(
        ..., 
        example="conll2003",
        description="ชื่อ dataset จาก Hugging Face"
    )
    model_name: str = Field(
        default="distilbert-base-uncased",
        description="ชื่อ base model"
    )
    epochs: int = Field(default=3, ge=1, le=100)
    batch_size: int = Field(default=16, ge=1, le=128)
    scheduled_time: Optional[str] = Field(
        default=None,
        description="เวลาเริ่มเทรน (ISO format: 2024-01-15T10:00:00)"
    )


class TrainingResponse(BaseModel):
    """Schema สำหรับ response"""
    job_id: str
    status: str
    message: str
    scheduled_time: Optional[str] = None


class TrainingJobStatus(BaseModel):
    """Schema สำหรับ status ของ job"""
    job_id: str
    status: str
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[dict] = None