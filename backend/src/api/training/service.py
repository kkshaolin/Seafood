from datetime import datetime
from redis.asyncio import Redis
from arq.connections import ArqRedis
import logging

logger = logging.getLogger(__name__)


class TrainingService:
    """Service สำหรับจัดการ training queue"""
    
    def __init__(self, redis: ArqRedis):
        self.redis = redis
    
    async def enqueue_training_job(
        self,
        job_id: str,
        dataset_name: str,
        model_name: str,
        epochs: int,
        batch_size: int,
        scheduled_time: Optional[str] = None
    ) -> dict:
        """
        เพิ่ม job เข้าคิวเทรนโมเดล
        ถ้ามี scheduled_time จะใช้ enqueue_at
        ถ้าไม่มี จะ enqueue ทันที
        """
        job_data = {
            "job_id": job_id,
            "dataset_name": dataset_name,
            "model_name": model_name,
            "epochs": epochs,
            "batch_size": batch_size,
            "created_at": datetime.now().isoformat()
        }
        
        if scheduled_time:
            # แปลงเวลาเป็น datetime object
            schedule_dt = datetime.fromisoformat(scheduled_time)
            
            # ARQ ใช้ enqueue_job with defer_by หรือ defer_until
            defer_until = schedule_dt.timestamp()
            
            await self.redis.enqueue_job(
                'train_model',
                job_data,
                job_id=job_id,
                _defer_until=defer_until
            )
            
            logger.info(f"Scheduled training job {job_id} at {scheduled_time}")
            return {
                "job_id": job_id,
                "status": "scheduled",
                "scheduled_time": scheduled_time,
                "message": f"Job จะเริ่มทำงานที่ {scheduled_time}"
            }
        else:
            # Enqueue ทันที
            await self.redis.enqueue_job(
                'train_model',
                job_data,
                job_id=job_id
            )
            
            logger.info(f"Enqueued training job {job_id}")
            return {
                "job_id": job_id,
                "status": "queued",
                "message": "Job ถูกเพิ่มเข้าคิวแล้ว"
            }
    
    async def get_job_status(self, job_id: str) -> dict:
        """ตรวจสอบสถานะ job"""
        job_result = await self.redis.job_result(job_id)
        
        if job_result is None:
            # ตรวจสอบว่า job ยังอยู่ใน queue หรือไม่
            job_info = await self.redis.all_job_results()
            return {
                "job_id": job_id,
                "status": "pending",
                "message": "Job ยังไม่เสร็จหรือไม่มีในระบบ"
            }
        
        return {
            "job_id": job_id,
            "status": "completed",
            "result": job_result
        }