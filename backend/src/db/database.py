"""Database session factory และ schema bootstrap สำหรับ SQLAlchemy Async.

นี่เป็นชั้นข้อมูลที่ main.py ใช้งานจริงสำหรับสร้าง session และสร้างตารางตอน startup;
การ import แบบ legacy ที่อ้างถึง api.auth / models.student เป็นรหัสเก่าที่ไม่ใช้งานในโครงสร้างปัจจุบัน.
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from core.config import settings

class Base(DeclarativeBase):
    pass


def _ensure_async_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return database_url


engine = create_async_engine(_ensure_async_database_url(settings.DATABASE_URL), pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def create_database_schema() -> None:
    # โหลด model ทั้งหมดก่อนสร้าง metadata เพื่อ SQLAlchemy รู้ว่าตารางใดบ้างจะถูกสร้าง
    # เส้นทางการใช้งานปัจจุบันใช้ model ของ stock อย่างชัดเจน
    from models import stock  # noqa: F401

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)