"""API สำหรับประเมินความเสี่ยงของสต็อกโดยเปรียบเทียบค่าทำนายกับค่าตรวจจับจากกล้อง.

Endpoint นี้คำนวณเปรียบเทียบค่าทำนาย (forecast_stock) กับค่าที่ตรวจพบจริง (detected_stock)
หรือ threshold ตาม risk preference เพื่อให้ UI แสดงสถานะ Normal / Warning / Critical ได้ทันที.
"""

from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel
from services.risk_service import RiskService

router = APIRouter(prefix="/risk", tags=["risk"])


class RiskEvaluationRequest(BaseModel):
    current_stock: Optional[float] = 0.0
    forecast_stock: float
    detected_stock: Optional[float] = None
    threshold: Optional[float] = 0.0
    risk_preference: Optional[str] = "balanced"


class RiskEvaluationResponse(BaseModel):
    risk_level: str
    current_stock: Optional[float] = 0.0
    forecast_stock: float
    detected_stock: Optional[float] = None
    diff_percent: Optional[float] = None
    threshold: Optional[float] = 0.0
    effective_threshold: Optional[float] = 0.0
    risk_preference: str
    reason: str


@router.post("/evaluate", response_model=RiskEvaluationResponse)
async def evaluate_risk(request: RiskEvaluationRequest):
    result = RiskService.evaluate_risk(
        current_stock=request.current_stock or 0.0,
        forecast_stock=request.forecast_stock,
        threshold=request.threshold or 0.0,
        risk_preference=request.risk_preference or "balanced",
        detected_stock=request.detected_stock
    )
    return RiskEvaluationResponse(**result)
