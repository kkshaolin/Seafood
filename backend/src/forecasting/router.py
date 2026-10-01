"""Router สำหรับจัดคิว forecast jobs และ queryผลลัพธ์จากฐานข้อมูล.

ด้วย compose.yml backend service จะประกาศอุปกรณ์และ worker ให้ทำงานภายใต้ Redis queue
ดังนั้น endpoint เหล่านี้ใช้สำหรับส่งงาน forecasting และตรวจสอบสถานะของ job.
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from arq import create_pool
from arq.connections import RedisSettings
from arq.jobs import Job, JobStatus
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from core.config import settings
from forecasting.schemas import ForecastRequest, ForecastJobResponse, ForecastJobStatusResponse, ForecastResponse, ForecastDataPoint, ForecastMetrics
from db.database import get_db_session
from models.stock import ForecastResult

router = APIRouter(prefix="/forecast", tags=["forecast"])

async def get_redis_pool():
    return await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))

@router.get("/latest", response_model=ForecastResponse)
async def get_latest_forecast(
    product: str,
    session: AsyncSession = Depends(get_db_session)
):
    try:
        stmt = select(ForecastResult).where(ForecastResult.product == product).order_by(desc(ForecastResult.created_at), ForecastResult.forecast_date)
        result = await session.execute(stmt)
        records = result.scalars().all()
        
        if not records:
            raise HTTPException(status_code=404, detail="No forecast found for this product")
            
        # Group by the latest created_at timestamp using a 60-second window
        from datetime import timedelta
        latest_created_at = records[0].created_at
        cutoff = latest_created_at - timedelta(seconds=60)
        latest_records = [r for r in records if r.created_at >= cutoff]
        
        # Sort chronologically
        latest_records.sort(key=lambda x: x.forecast_date)
        
        points = []
        for r in latest_records:
            points.append(ForecastDataPoint(
                date=r.forecast_date,
                predicted_value=r.predicted_value,
                lower_bound=r.lower_bound,
                upper_bound=r.upper_bound
            ))
            
        return ForecastResponse(
            product=product,
            model_name=latest_records[0].model_name,
            metrics=ForecastMetrics(mae=0, rmse=0, mape=0), # Can't fetch metrics from DB easily without a separate table, hardcode to 0 for display
            forecast=points,
            model_uri=latest_records[0].model_version
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("", response_model=ForecastJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def queue_arima_forecast(
    req: ForecastRequest,
    redis=Depends(get_redis_pool)
):
    try:
        job_id = str(uuid.uuid4())
        # Enqueue job to forecasting_queue
        await redis.enqueue_job(
            "run_forecast_task",
            req.model_dump(),
            _job_id=job_id,
            _queue_name="forecasting_queue"
        )
        return ForecastJobResponse(job_id=job_id, status="queued")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue forecast job: {str(e)}")

@router.post("/train", response_model=ForecastJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def queue_arima_training(
    req: ForecastRequest,
    redis=Depends(get_redis_pool)
):
    try:
        job_id = str(uuid.uuid4())
        await redis.enqueue_job(
            "run_training_task",
            req.model_dump(),
            _job_id=job_id,
            _queue_name="training_queue"
        )
        return ForecastJobResponse(job_id=job_id, status="queued")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue training job: {str(e)}")

@router.get("/{job_id}", response_model=ForecastJobStatusResponse)
async def get_forecast_job_status(
    job_id: str,
    redis=Depends(get_redis_pool)
):
    try:
        job = Job(job_id, redis, _queue_name="forecasting_queue")
        job_status = await job.status()
        
        if job_status == JobStatus.not_found:
            job = Job(job_id, redis, _queue_name="training_queue")
            job_status = await job.status()
            
        if job_status == JobStatus.not_found:
            raise HTTPException(status_code=404, detail="Job not found")
            
        status_str = "queued"
        if job_status == JobStatus.in_progress:
            status_str = "running"
        elif job_status == JobStatus.complete:
            status_str = "completed"
            
        info = await job.info()
        result = None
        error = None
        
        if status_str == "completed":
            job_result = await job.result()
            if isinstance(job_result, dict) and job_result.get("status") == "error":
                status_str = "failed"
                error = job_result.get("error")
            else:
                result = job_result
                
        return ForecastJobStatusResponse(
            status=status_str,
            result=result,
            error=error
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
