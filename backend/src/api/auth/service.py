from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.model import User
from api.auth.repository import AuthRepository
from core.config import settings
from db.database import get_db_session

password_hash = PasswordHash.recommended()
bearer_scheme = HTTPBearer()


class InvalidCredentialsError(Exception):
    pass


class EmailAlreadyExistsError(Exception):
    pass


class AuthService:
    def __init__(self, repository: AuthRepository) -> None:
        self.repository = repository

    async def login(self, email: str, password: str) -> str:
        user = await self.repository.get_user_by_email(email)
        if user is None or not password_hash.verify(password, user.password_hash):
            raise InvalidCredentialsError

        expires_at = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
        return jwt.encode(
            {"sub": str(user.id), "email": user.email, "exp": expires_at},
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )

    async def register(self, email: str, password: str) -> User:
        existing = await self.repository.get_user_by_email(email)
        if existing is not None:
            raise EmailAlreadyExistsError

        hashed = password_hash.hash(password)
        return await self.repository.create_user(email, hashed)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    """JWT dependency — ใส่ใน controller ที่ต้องการ auth."""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id: int = int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    repo = AuthRepository(session)
    user = await repo.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user
