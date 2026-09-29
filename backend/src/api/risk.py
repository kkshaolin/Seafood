from fastapi import APIRouter
from pydantic import BaseModel
from services.risk_service import RiskService

router = APIRouter(prefix="/risk", tags=["risk"])

class RiskEvaluationRequest(BaseModel):
    current_stock: float
    forecast_stock: float
    threshold: float
    risk_preference: str

class RiskEvaluationResponse(BaseModel):
    risk_level: str
    current_stock: float
    forecast_stock: float
    threshold: float
    effective_threshold: float
    risk_preference: str
    reason: str

@router.post("/evaluate", response_model=RiskEvaluationResponse)
async def evaluate_risk(request: RiskEvaluationRequest):
    result = RiskService.evaluate_risk(
        current_stock=request.current_stock,
        forecast_stock=request.forecast_stock,
        threshold=request.threshold,
        risk_preference=request.risk_preference
    )
    return RiskEvaluationResponse(**result)
