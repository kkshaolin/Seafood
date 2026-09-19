from fastapi import APIRouter, status
from api.predict.controller import predict
from api.predict.schema import InferenceResponse

router = APIRouter(tags=["predict"])

router.add_api_route("/predict", predict, methods=["POST"], response_model=InferenceResponse, status_code=status.HTTP_200_OK)
