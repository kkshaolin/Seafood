"""จุดเริ่มต้น ARQ สำหรับฝึกและบันทึกโมเดลพยากรณ์

Compose เปิด ``training-worker`` ด้วย
``training_worker.worker.WorkerSettings`` บนคิว ``training_queue``.
แต่ละงานจะตรวจคำขอ เปิด session ฐานข้อมูล แล้วเรียก ForecastingService
เพื่อคำนวณตัวชี้วัดและบันทึกโมเดลที่ฝึกเสร็จ
"""
import os
import sys
import logging
from arq.connections import RedisSettings

# เพิ่ม source ของ backend และ inference worker เพื่อใช้ session, schema และบริการโมเดลร่วมกัน
workspace_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
backend_src = os.path.join(workspace_root, "backend", "src")
inference_src = os.path.join(workspace_root, "workers", "inference_worker")
if backend_src not in sys.path:
    sys.path.insert(0, backend_src)
if inference_src not in sys.path:
    sys.path.insert(0, inference_src)

from db.database import SessionLocal
from inference_worker.forecast_model.service import ForecastingService
from forecasting.schemas import ForecastRequest

logger = logging.getLogger("training_worker")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

async def startup(ctx):
    """บันทึกข้อความเมื่อ ARQ เริ่ม worker ฝึกโมเดล"""
    logger.info("Training Worker starting up...")

async def shutdown(ctx):
    """บันทึกข้อความเมื่อ ARQ ปิด worker ฝึกโมเดล"""
    logger.info("Training Worker shutting down...")

async def run_training_task(ctx, req_data: dict) -> dict:
    """
    ประมวลผลงานฝึกโมเดลหนึ่งรายการที่ส่งผ่าน ARQ

    ตรวจคำขอ เปิด session ฐานข้อมูล เรียกขั้นตอนฝึกและคืนผลเป็น dict;
    หากเกิดข้อผิดพลาดจะบันทึก stack trace และคืนสถานะ error ให้ผู้เรียก
    """
    job_id = ctx.get("job_id", "unknown")
    logger.info(f"Starting training job {job_id}")
    
    try:
        req = ForecastRequest(**req_data)
        async with SessionLocal() as session:
            service = ForecastingService(session)
            result = await service.run_training(req)
            logger.info(f"Training job {job_id} completed successfully")
            return result.model_dump()
    except Exception as e:
        logger.error(f"Training job {job_id} failed: {str(e)}", exc_info=True)
        return {"status": "error", "error": str(e)}

class WorkerSettings:
    """กำหนดคิวฝึกโมเดล การเชื่อมต่อ Redis และขีดจำกัดงานพร้อมกัน"""
    functions = [run_training_task]
    queue_name = "training_queue"
    job_timeout = 600 # 10 minutes max
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://redis:6379"))
    max_jobs = 1
    poll_delay = 0.5
