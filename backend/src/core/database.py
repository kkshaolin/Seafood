"""
Database connection module
สร้าง engine และ session สำหรับเชื่อมต่อ PostgreSQL
"""
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from core.config import settings


# แปลง DATABASE_URL เป็น async version
DATABASE_URL = settings.DATABASE_URL
if DATABASE_URL.startswith("postgresql+asyncpg://"):
    ASYNC_DATABASE_URL = DATABASE_URL
elif DATABASE_URL.startswith("postgresql://"):
    ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgres://"):
    ASYNC_DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
else:
    raise ValueError(
        "DATABASE_URL must use a PostgreSQL scheme like postgres:// or postgresql://"
    )

# สร้าง async engine
engine = create_async_engine(
    ASYNC_DATABASE_URL,
    echo=True,  # แสดง SQL queries (สำหรับ debug)
    future=True,
)

# สร้าง async session factory
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# Base class สำหรับ models
class Base(DeclarativeBase):
    pass


# ฟังก์ชันสำหรับ get session (ใช้ dependency injection)
# async def get_session() -> AsyncSession:
#     """
#     สร้าง session สำหรับใช้งาน
#     ใช้ใน FastAPI dependency injection
#     """
#     async with async_session() as session:
#         yield session
async def get_session() -> AsyncIterator[AsyncSession]:
    async with async_session() as session:
        yield session