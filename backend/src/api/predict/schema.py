from pydantic import BaseModel, Field
from typing import Any, List

class InferenceRequest(BaseModel):
    model_uri: str = Field(..., description="MLflow model URI (e.g. models:/my_model/1 or runs:/<run_id>/model)", example="runs:/abc123def456/model")
    input_data: List[Any] = Field(..., max_length=100, description="Data to run prediction on (Max 100 items per request)", example=["The quick brown fox."])

class InferenceResponse(BaseModel):
    status: str
    model_uri: str
    predictions: Any
    job_id: str
