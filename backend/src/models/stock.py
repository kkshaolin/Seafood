"""Model SQLAlchemy สำหรับข้อมูลสต็อกและผลลัพธ์การพยากรณ์.

ตารางที่นิยามตรงนี้เป็น core schema ที่ใช้งานจริงในระบบ stock + forecast workflow
และจะถูกสร้างโดย create_database_schema() ใน db/database.py ตอน backend start.
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Integer, String, Float, DateTime, Date, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base

class ShrimpStockData(Base):
    """ข้อมูล Stock Time Series"""
    __tablename__ = "shrimp_stocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    product: Mapped[str] = mapped_column(String(50), index=True)
    quantity: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(20), default="kg", server_default="kg")
    warehouse: Mapped[Optional[str]] = mapped_column(String(100))
    source: Mapped[Optional[str]] = mapped_column(String(50))  # e.g., 'camera', 'manual', 'csv'
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CameraLog(Base):
    """บันทึกผลการทำงานจากกล้องและ YOLO"""
    __tablename__ = "camera_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camera_id: Mapped[str] = mapped_column(String(50), index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    image_path: Mapped[str] = mapped_column(Text)
    detected_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    processing_status: Mapped[str] = mapped_column(String(20))  # e.g., 'pending', 'processed', 'failed'
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SystemSetting(Base):
    """การตั้งค่าของระบบ เช่น risk preference"""
    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    value: Mapped[str] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ForecastResult(Base):
    """ผลลัพธ์จากโมเดลพยากรณ์ เช่น ARIMA"""
    __tablename__ = "forecast_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product: Mapped[str] = mapped_column(String(50), index=True)
    forecast_date: Mapped[date] = mapped_column(Date, index=True)
    predicted_value: Mapped[float] = mapped_column(Float)
    lower_bound: Mapped[Optional[float]] = mapped_column(Float)
    upper_bound: Mapped[Optional[float]] = mapped_column(Float)
    model_name: Mapped[str] = mapped_column(String(100))
    model_version: Mapped[Optional[str]] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
