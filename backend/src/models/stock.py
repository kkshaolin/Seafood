"""Model SQLAlchemy สำหรับข้อมูลสต็อกและผลลัพธ์การพยากรณ์.

ตารางที่นิยามตรงนี้เป็น core schema ที่ใช้งานจริงในระบบ stock + forecast workflow
และจะถูกสร้างโดย create_database_schema() ใน db/database.py ตอน backend start.
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Integer, String, Float, DateTime, Date, Time, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base

class InventorySummary(Base):
    """ข้อมูล Inventory Summary จากคลังสินค้า"""
    __tablename__ = "inventory_summaries"
    __table_args__ = (
        UniqueConstraint("date", "time", "split", name="uq_inventory_summary_observation"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    image_path: Mapped[str] = mapped_column(String(255))
    split: Mapped[str] = mapped_column(String(50))
    date: Mapped[date] = mapped_column(Date, index=True)
    time: Mapped[str] = mapped_column(String(10))
    total_boxes: Mapped[int] = mapped_column(Integer)
    total_weight_kg: Mapped[float] = mapped_column(Float)
    occupied_slots: Mapped[int] = mapped_column(Integer)
    empty_slots: Mapped[int] = mapped_column(Integer)
    occupancy_pct: Mapped[float] = mapped_column(Float)
    boxes_level1: Mapped[int] = mapped_column(Integer)
    boxes_level2: Mapped[int] = mapped_column(Integer)
    boxes_level3: Mapped[int] = mapped_column(Integer)
    boxes_level4: Mapped[int] = mapped_column(Integer)
    inbound_boxes: Mapped[int] = mapped_column(Integer)
    outbound_boxes: Mapped[int] = mapped_column(Integer)
    cold_room_temp_c: Mapped[float] = mapped_column(Float)
    humidity_pct: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())



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
    model_version: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# =====================================================================
# โครงสร้างตารางใหม่ (4 ตารางหลัก + ตารางรายปี)
# time, product, boxes_A, boxes_B, total_boxes
# =====================================================================

from sqlalchemy import BigInteger

class BoxLog(Base):
    """1. การเก็บค่าจากกล่อง / กล้องตรวจจับ (Box Detection Logs)"""
    __tablename__ = "box_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), index=True)
    product: Mapped[str] = mapped_column(String(100), default="Frozen Shrimp", index=True)
    boxes_A: Mapped[int] = mapped_column("boxes_a", Integer, default=0)
    boxes_B: Mapped[int] = mapped_column("boxes_b", Integer, default=0)
    total_boxes: Mapped[int] = mapped_column(Integer, default=0)
    camera_id: Mapped[Optional[str]] = mapped_column(String(50))
    image_path: Mapped[Optional[str]] = mapped_column(String(255))
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DailyInventory(Base):
    """2. คลังสินค้ารายวัน (Daily Inventories)"""
    __tablename__ = "daily_inventories"
    __table_args__ = (
        UniqueConstraint("time", "product", name="uq_daily_inventories_time_product"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    time: Mapped[date] = mapped_column(Date, index=True)
    product: Mapped[str] = mapped_column(String(100), default="Frozen Shrimp")
    boxes_A: Mapped[int] = mapped_column("boxes_a", Integer, default=0)
    boxes_B: Mapped[int] = mapped_column("boxes_b", Integer, default=0)
    total_boxes: Mapped[int] = mapped_column(Integer, default=0)
    inbound_boxes: Mapped[int] = mapped_column(Integer, default=0)
    outbound_boxes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MonthlyInventory(Base):
    """3. คลังสินค้ารายเดือน (Monthly Inventories - สำหรับเทรนและป้อนเข้า ARIMA)"""
    __tablename__ = "monthly_inventories"
    __table_args__ = (
        UniqueConstraint("time", "product", name="uq_monthly_inventories_time_product"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    time: Mapped[date] = mapped_column(Date, index=True)  # เช่น 2021-01-01
    product: Mapped[str] = mapped_column(String(100), default="Frozen Shrimp")
    boxes_A: Mapped[int] = mapped_column("boxes_a", Integer, default=0)
    boxes_B: Mapped[int] = mapped_column("boxes_b", Integer, default=0)
    total_boxes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class YearlyInventory(Base):
    """3.1 คลังสินค้ารายปี (Yearly Inventories)"""
    __tablename__ = "yearly_inventories"
    __table_args__ = (
        UniqueConstraint("time", "product", name="uq_yearly_inventories_time_product"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    time: Mapped[date] = mapped_column(Date, index=True)  # เช่น 2021-01-01
    product: Mapped[str] = mapped_column(String(100), default="Frozen Shrimp")
    boxes_A: Mapped[int] = mapped_column("boxes_a", Integer, default=0)
    boxes_B: Mapped[int] = mapped_column("boxes_b", Integer, default=0)
    total_boxes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ArimaForecast(Base):
    """4. ค่าทำนายจาก ARIMA (ARIMA Forecasts)"""
    __tablename__ = "arima_forecasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    time: Mapped[date] = mapped_column(Date, index=True)  # เช่น 2024-04-01
    product: Mapped[str] = mapped_column(String(100), default="Frozen Shrimp", index=True)
    boxes_A: Mapped[Optional[float]] = mapped_column("boxes_a", Float)
    boxes_B: Mapped[Optional[float]] = mapped_column("boxes_b", Float)
    total_boxes: Mapped[float] = mapped_column(Float)  # ค่าพยากรณ์สต็อกรวม
    lower_bound: Mapped[Optional[float]] = mapped_column(Float)
    upper_bound: Mapped[Optional[float]] = mapped_column(Float)
    model_order: Mapped[str] = mapped_column(String(50), default="ARIMA(1,1,1)")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

