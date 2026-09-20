from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.model import User
from api.auth.service import get_current_user
from db.database import get_db_session
from models.market_data import IngestionRun

router = APIRouter(prefix="/ingestion", tags=["ingestion"])

DATA_QUEUE = "data_queue"
TASKS = {
    "prices": "ingest_prices_task",
    "financials": "ingest_financials_task",
    "trade": "ingest_trade_task",
}


class IngestParams(BaseModel):
    symbols: Optional[list[str]] = None  # prices/financials: เช่น ["TU", "SSF"] (ไม่ใส่ = ใช้ค่า default ใน env)
    backfill: bool = False               # prices: ดึงย้อนหลังเต็ม
    start: Optional[str] = None          # prices: YYYY-MM-DD
    source: Optional[str] = None         # trade: ชื่อ source ใน trade_sources.yml
    months_back: Optional[int] = None    # trade: url_template ย้อนกี่เดือน
    force: bool = False                  # trade: โหลดทับแม้ไฟล์ไม่เปลี่ยน


@router.post("/{dataset}", status_code=status.HTTP_202_ACCEPTED)
async def trigger_ingestion(
    dataset: Literal["prices", "financials", "trade"],
    request: Request,
    params: IngestParams = IngestParams(),
    current_user: User = Depends(get_current_user),
) -> dict:
    """สั่งรัน ingestion ทันที (ปกติ Data Worker รันเองตาม cron) — คืน job_id ไว้เช็คที่ /job_status/{job_id}"""
    if dataset == "prices":
        args = (params.symbols, params.backfill, params.start)
    elif dataset == "financials":
        args = (params.symbols,)
    else:
        args = (params.source, params.months_back, params.force)

    # prefix "ingest_" ทำให้ GET /job_status/{job_id} รู้ว่าต้องไปดูคิว data_queue
    job_id = f"ingest_{dataset}_{datetime.now():%Y%m%d_%H%M%S}"
    job = await request.app.state.redis_pool.enqueue_job(
        TASKS[dataset], *args, _job_id=job_id, _queue_name=DATA_QUEUE
    )
    if job is None:
        raise HTTPException(status_code=409, detail="A job with the same id is already queued")
    return {"status": "queued", "dataset": dataset, "job_id": job.job_id}


@router.get("/runs")
async def list_runs(
    dataset: Optional[str] = None,
    limit: int = 20,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """ประวัติการรัน ingestion ล่าสุด"""
    q = select(
        IngestionRun.id, IngestionRun.dataset, IngestionRun.status, IngestionRun.records_written,
        IngestionRun.object_key, IngestionRun.started_at, IngestionRun.finished_at,
    ).order_by(IngestionRun.id.desc()).limit(min(max(limit, 1), 200))
    if dataset:
        q = q.where(IngestionRun.dataset == dataset)
    return [dict(r._mapping) for r in await session.execute(q)]
