from fastapi import APIRouter, HTTPException, Depends
from arq.connections import ArqRedis, create_pool
from redis.asyncio import Redis
from .schema import TrainingRequest, TrainingResponse, TrainingJobStatus
from .service import TrainingService
from datetime import datetime
import uuid

router = APIRouter(prefix="/api/training", tags=["training"])


async def get_arq_redis() -> ArqRedis:
    """Dependency สำหรับ ARQ Redis connection"""
    redis = await create_pool({
        'host': 'redis',
        'port': 6379,
    })
    return redis


@router.post("/add_train_queue_time", response_model=TrainingResponse)
async def add_train_queue_time(request: TrainingRequest):
    """
    เพิ่ม job เข้าคิวเทรนโมเดล
    สามารถกำหนดเวลาเริ่มทำงานได้ (scheduled_time)
    """
    try:
        redis = await get_arq_redis()
        service = TrainingService(redis)
        
        # สร้าง job_id แบบ unique
        job_id = f"train_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        result = await service.enqueue_training_job(
            job_id=job_id,
            dataset_name=request.dataset_name,
            model_name=request.model_name,
            epochs=request.epochs,
            batch_size=request.batch_size,
            scheduled_time=request.scheduled_time
        )
        
        return TrainingResponse(**result)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/job_status/{job_id}", response_model=TrainingJobStatus)
async def get_job_status(job_id: str):
    """ตรวจสอบสถานะ job"""
    try:
        redis = await get_arq_redis()
        service = TrainingService(redis)
        result = await service.get_job_status(job_id)
        return TrainingJobStatus(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))