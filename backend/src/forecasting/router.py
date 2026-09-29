import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from arq import create_pool
from arq.connections import RedisSettings
from arq.jobs import Job, JobStatus

from core.config import settings
from forecasting.schemas import ForecastRequest, ForecastJobResponse, ForecastJobStatusResponse

router = APIRouter(prefix="/forecast", tags=["forecast"])

async def get_redis_pool():
    return await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))

@router.post("", response_model=ForecastJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def queue_arimax_forecast(
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

@router.get("/{job_id}", response_model=ForecastJobStatusResponse)
async def get_forecast_job_status(
    job_id: str,
    redis=Depends(get_redis_pool)
):
    try:
        job = Job(job_id, redis, _queue_name="forecasting_queue")
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
