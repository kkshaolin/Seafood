from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.model import User
from api.auth.repository import AuthRepository
from api.auth.schema import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from api.auth.service import AuthService, EmailAlreadyExistsError, InvalidCredentialsError, get_current_user
from db.database import get_db_session


async def login(payload: LoginRequest, session: AsyncSession = Depends(get_db_session)) -> TokenResponse:
    service = AuthService(AuthRepository(session))
    try:
        token = await service.login(payload.email, payload.password)
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    return TokenResponse(access_token=token)


async def register(payload: RegisterRequest, session: AsyncSession = Depends(get_db_session)) -> UserResponse:
    service = AuthService(AuthRepository(session))
    try:
        user = await service.register(payload.email, payload.password)
    except EmailAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        ) from None
    return UserResponse.model_validate(user)


async def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)
