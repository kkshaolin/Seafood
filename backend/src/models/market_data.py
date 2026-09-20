"""
ตารางสำหรับข้อมูลที่ Data Worker ดึงมา (ราคาหุ้น/ค่าเงิน, งบการเงิน, ประวัติการรัน)
Worker เขียนด้วย upsert ตามชื่อคอลัมน์ในไฟล์นี้ (workers/ingestion/db.py) — แก้ schema ที่นี่แล้วออก Alembic migration
"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import BigInteger, Date, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base


class MarketPrice(Base):
    """ราคารายวัน (หุ้น SET กลุ่มอาหารทะเล + คู่เงิน) 1 แถว = 1 symbol x 1 วัน"""
    __tablename__ = "market_prices"

    symbol: Mapped[str] = mapped_column(String(24), primary_key=True)
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    asset_type: Mapped[str] = mapped_column(String(10))  # equity | fx
    open: Mapped[Optional[float]] = mapped_column(Float)
    high: Mapped[Optional[float]] = mapped_column(Float)
    low: Mapped[Optional[float]] = mapped_column(Float)
    close: Mapped[Optional[float]] = mapped_column(Float)
    adj_close: Mapped[Optional[float]] = mapped_column(Float)
    volume: Mapped[Optional[int]] = mapped_column(BigInteger)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FinancialStatement(Base):
    """งบการเงินแบบ long format: 1 แถว = 1 บริษัท x 1 ไตรมาส x 1 งบ x 1 รายการ"""
    __tablename__ = "financial_statements"

    symbol: Mapped[str] = mapped_column(String(24), primary_key=True)
    period_end: Mapped[date] = mapped_column(Date, primary_key=True)
    statement: Mapped[str] = mapped_column(String(10), primary_key=True)  # income | balance | cashflow
    line_item: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[Optional[float]] = mapped_column(Float)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IngestionRun(Base):
    """ประวัติการรัน ingestion แต่ละครั้ง (ใช้ดูว่าข้อมูลล่าสุดมาเมื่อไหร่/พังตรงไหน)"""
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset: Mapped[str] = mapped_column(String(40), index=True)  # prices | financials | trade
    status: Mapped[str] = mapped_column(String(12))  # running | success | partial | failed | skipped
    records_written: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    object_key: Mapped[Optional[str]] = mapped_column(Text)
    detail: Mapped[Optional[str]] = mapped_column(Text)  # JSON string
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
