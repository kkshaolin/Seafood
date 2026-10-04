"""API Router สำหรับระบบ Camera Sampling และตรวจสอบ Box Logs.

จัดคิวงาน run_sampling_task เข้า Redis queue 'sampling_queue'
เพื่อให้ sampling_worker ทำการครอปเฟรมภาพจากกล้อง Zone A และ Zone B
อัปโหลดเข้า MinIO bucket 'sampling-camera' (โฟลเดอร์ ZoneA/ และ ZoneB/)
และบันทึกประวัติการตรวจนับลงตาราง box_logs ใน PostgreSQL.
"""

import os
import uuid
from datetime import datetime
from typing import List, Optional

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from db.database import get_db_session
from models.stock import BoxLog

router = APIRouter(prefix="/sampling", tags=["sampling"])


async def get_redis_pool():
    return await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))


class SamplingJobResponse(BaseModel):
    job_id: str
    status: str
    message: str
    queue: str = "sampling_queue"


class BoxLogResponse(BaseModel):
    id: int
    time: datetime
    product: str
    boxes_A: int
    boxes_B: int
    total_boxes: int
    camera_id: Optional[str] = None
    image_path: Optional[str] = None
    confidence: Optional[float] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SamplingStatusResponse(BaseModel):
    bucket: str
    zone_a_folder: str
    zone_b_folder: str
    daily_schedule_enabled: bool
    total_samples: int
    latest_sample_time: Optional[datetime] = None


@router.post("/capture", response_model=SamplingJobResponse, status_code=status.HTTP_202_ACCEPTED,
             summary="สั่งดึงภาพจากกล้องทั้ง 2 ตัว ครอปภาพ และอัปโหลดขึ้น MinIO ทันที")
async def trigger_camera_sampling(redis=Depends(get_redis_pool)):
    """สั่งงาน Sampling ผ่าน ARQ sampling_queue.

    Worker จะดึงเฟรมจาก mockA.mp4 (Zone A) และ mockB.mp4 (Zone B),
    ครอปบริเวณตรวจนับ, อัปโหลดเข้า MinIO bucket 'sampling-camera',
    และบันทึกจำนวนกล่องลงตาราง 'box_logs'
    """
    try:
        job_id = str(uuid.uuid4())
        await redis.enqueue_job(
            "run_sampling_task",
            _job_id=job_id,
            _queue_name="sampling_queue",
        )
        return SamplingJobResponse(
            job_id=job_id,
            status="queued",
            message="Camera sampling task successfully queued to sampling_queue",
            queue="sampling_queue",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to queue camera sampling task: {str(e)}",
        )


@router.get("/status", response_model=SamplingStatusResponse, summary="ตรวจสอบสถานะการตั้งค่า Sampling")
async def get_sampling_status(session: AsyncSession = Depends(get_db_session)):
    """ตรวจสอบสถานะของ sampling-camera bucket, ค่า daily schedule และจำนวนครั้งที่ sample ไปแล้ว"""
    try:
        count_stmt = select(func.count(BoxLog.id))
        count_res = await session.execute(count_stmt)
        total_count = count_res.scalar() or 0

        latest_stmt = select(BoxLog.time).order_by(desc(BoxLog.time)).limit(1)
        latest_res = await session.execute(latest_stmt)
        latest_time = latest_res.scalar_one_or_none()

        daily_enabled = os.getenv("DAILY_SAMPLING_ENABLED", "false").lower() in ("true", "1", "yes")

        return SamplingStatusResponse(
            bucket=os.getenv("SAMPLING_BUCKET", "sampling-camera"),
            zone_a_folder="ZoneA/",
            zone_b_folder="ZoneB/",
            daily_schedule_enabled=daily_enabled,
            total_samples=total_count,
            latest_sample_time=latest_time,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs", response_model=List[BoxLogResponse], summary="ดึงรายการประวัติที่บันทึกลง box_logs")
async def list_box_logs(limit: int = 20, session: AsyncSession = Depends(get_db_session)):
    """ดึงข้อมูลรายการล่าสุดจากตาราง box_logs"""
    try:
        stmt = select(BoxLog).order_by(desc(BoxLog.time)).limit(limit)
        res = await session.execute(stmt)
        return res.scalars().all()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
