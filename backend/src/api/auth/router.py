from fastapi import APIRouter, status

from api.auth.controller import get_me, login, register
from api.auth.schema import TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])
router.add_api_route("/login", login, methods=["POST"], response_model=TokenResponse, status_code=status.HTTP_200_OK)
router.add_api_route("/register", register, methods=["POST"], response_model=UserResponse, status_code=status.HTTP_201_CREATED)
router.add_api_route("/me", get_me, methods=["GET"], response_model=UserResponse, status_code=status.HTTP_200_OK)
