"""จุดเริ่มต้น ARQ สำหรับงานนำเข้าข้อมูลภายนอกของระบบ

Compose เปิด worker นี้ด้วย ``data_worker.worker.WorkerSettings`` บนคิว ``data_queue``.
หน้าที่หลักคือแปลงงาน ARQ เป็นการเรียก ingestion สำหรับราคา งบการเงิน และสถิติการค้า
พร้อมตั้งงานตามเวลา โดยงานสถิติการค้าจะข้ามการดึงข้อมูลหากยังไม่มี source ที่เปิดใช้งาน

ขั้นตอนตามชนิดข้อมูล:
  prices     : ราคาหุ้นอาหารทะเล + ค่าเงิน (รายวัน)      -> MinIO raw-financial + PostgreSQL
  financials : งบการเงิน/กำไรขาดทุน (รายไตรมาส)          -> PostgreSQL + Redis cache
  trade      : สถิติส่งออกกุ้ง/หมึกแช่แข็ง (รายเดือน)     -> MinIO raw-trade

งาน cron อิงเขตเวลาของคอนเทนเนอร์ ซึ่ง Compose กำหนดเป็น Asia/Bangkok
"""
import asyncio
import logging
import os
from datetime import date
from typing import Optional

from arq import cron
from arq.connections import RedisSettings

from data_worker.ingestion import financials, stocks, trade

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | data_worker | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("data_worker")


async def startup(ctx):
    """บันทึกการเริ่มต้น worker และชื่อคิวที่ใช้รับงาน"""
    logger.info("Data worker starting (queue=data_queue)")


async def ingest_prices_task(ctx, symbols: Optional[list] = None, backfill: bool = False,
                             start: Optional[str] = None) -> dict:
    """แปลงวันที่เริ่มต้น แล้วส่งงานดึงราคาแบบ synchronous ไปทำใน thread"""
    start_date = date.fromisoformat(start) if start else None
    return await asyncio.to_thread(stocks.ingest_prices, symbols, backfill, start_date)


async def ingest_financials_task(ctx, symbols: Optional[list] = None) -> dict:
    """เรียกกระบวนการดึงงบการเงินโดยไม่บล็อก event loop ของ ARQ"""
    return await asyncio.to_thread(financials.ingest_financials, symbols)


async def ingest_trade_task(ctx, source: Optional[str] = None, months_back: Optional[int] = None,
                            force: bool = False) -> dict:
    """เรียกกระบวนการเก็บไฟล์สถิติการค้าตาม source และช่วงย้อนหลังที่ระบุ"""
    return await asyncio.to_thread(trade.ingest_trade, source, months_back, force)


class WorkerSettings:
    """กำหนดคิว ฟังก์ชัน งานตามเวลา และขีดจำกัดการทำงานของ data worker"""
    functions = [ingest_prices_task, ingest_financials_task, ingest_trade_task]
    queue_name = "data_queue"
    cron_jobs = [
        # ราคาหุ้น/FX: จันทร์-ศุกร์ 17:30 (ตลาด SET ปิด 16:30)
        cron(ingest_prices_task, weekday={0, 1, 2, 3, 4}, hour=17, minute=30),
        # งบการเงิน: อาทิตย์ 03:00 (Yahoo ให้ย้อนหลังสั้น จึงรันถี่กว่ารอบไตรมาสเพื่อสะสม)
        cron(ingest_financials_task, weekday=6, hour=3, minute=0),
        # สถิติส่งออก: จันทร์ 04:00 (ข้ามไฟล์ที่ไม่เปลี่ยนด้วย sha256 จึงรันถี่ได้)
        cron(ingest_trade_task, weekday=0, hour=4, minute=0),
    ]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://redis:6379"))
    job_timeout = 3600
    max_jobs = 3
    max_tries = 2
