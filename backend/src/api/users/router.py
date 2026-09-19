from fastapi import APIRouter, status

from api.auth.schema import UserResponse
from api.users.controller import delete_user, get_all_users, get_user, update_user

router = APIRouter(prefix="/users", tags=["users"])
router.add_api_route("", get_all_users, methods=["GET"], response_model=list[UserResponse], status_code=status.HTTP_200_OK)
router.add_api_route("/{user_id}", get_user, methods=["GET"], response_model=UserResponse, status_code=status.HTTP_200_OK)
router.add_api_route("/{user_id}", update_user, methods=["PATCH"], response_model=UserResponse, status_code=status.HTTP_200_OK)
router.add_api_route("/{user_id}", delete_user, methods=["DELETE"], status_code=status.HTTP_200_OK)
