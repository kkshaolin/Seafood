"""Data Worker (ARQ) — ดึงข้อมูลจากภายนอกเข้าระบบ ตามแผน Data Sources & Ingestion Plan

  prices     : ราคาหุ้นอาหารทะเล + ค่าเงิน (รายวัน)      -> MinIO raw-financial + PostgreSQL
  financials : งบการเงิน/กำไรขาดทุน (รายไตรมาส)          -> PostgreSQL + Redis cache
  trade      : สถิติส่งออกกุ้ง/หมึกแช่แข็ง (รายเดือน)     -> MinIO raw-trade

รัน:  python -m arq data_worker.WorkerSettings      (คิว: data_queue)
Cron ใช้เวลาตาม TZ ของคอนเทนเนอร์ (compose ตั้ง TZ=Asia/Bangkok)
"""
import asyncio
import logging
import os
from datetime import date
from typing import Optional

from arq import cron
from arq.connections import RedisSettings

from ingestion import financials, stocks, trade

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | data_worker | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("data_worker")


async def startup(ctx):
    logger.info("Data worker starting (queue=data_queue)")


async def ingest_prices_task(ctx, symbols: Optional[list] = None, backfill: bool = False,
                             start: Optional[str] = None) -> dict:
    start_date = date.fromisoformat(start) if start else None
    return await asyncio.to_thread(stocks.ingest_prices, symbols, backfill, start_date)


async def ingest_financials_task(ctx, symbols: Optional[list] = None) -> dict:
    return await asyncio.to_thread(financials.ingest_financials, symbols)


async def ingest_trade_task(ctx, source: Optional[str] = None, months_back: Optional[int] = None,
                            force: bool = False) -> dict:
    return await asyncio.to_thread(trade.ingest_trade, source, months_back, force)


class WorkerSettings:
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
