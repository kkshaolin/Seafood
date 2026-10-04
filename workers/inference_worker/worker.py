"""จุดเริ่มต้น ARQ สำหรับประมวลผลคำขอพยากรณ์

Compose เปิดโมดูลนี้เป็น ``forecasting-worker`` ด้วย
``inference_worker.worker.WorkerSettings`` ซึ่งรับงานจากคิว ``forecasting_queue``.
ตัว worker เตรียม path สำหรับ backend, เปิด session ฐานข้อมูลต่อ job
แล้วส่งคำขอที่ตรวจรูปแบบแล้วให้ ForecastingService ประมวลผลและบันทึกผล
"""
import os
import sys
import logging
from arq.connections import RedisSettings

# เพิ่ม source ของ backend ลงใน path เพื่อให้ worker ใช้ schema และ session ร่วมกันได้
workspace_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
backend_src = os.path.join(workspace_root, "backend", "src")
if backend_src not in sys.path:
    sys.path.insert(0, backend_src)

from db.database import SessionLocal
from inference_worker.forecast_model.service import ForecastingService
from forecasting.schemas import ForecastRequest

logger = logging.getLogger("forecasting_worker")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

async def startup(ctx):
    """บันทึกข้อความเมื่อ ARQ เริ่ม worker สำหรับคิวพยากรณ์"""
    logger.info("Forecasting Worker starting up...")

async def shutdown(ctx):
    """บันทึกข้อความเมื่อ ARQ ปิด worker สำหรับคิวพยากรณ์"""
    logger.info("Forecasting Worker shutting down...")

async def run_forecast_task(ctx, req_data: dict) -> dict:
    """
    ประมวลผลงานพยากรณ์หนึ่งรายการที่ส่งผ่าน ARQ

    ตรวจข้อมูลคำขอ สร้าง session ฐานข้อมูล เรียกบริการพยากรณ์ และคืนผลเป็น dict;
    หากเกิดข้อผิดพลาดจะบันทึก stack trace และคืนสถานะ error ให้ผู้เรียก
    """
    job_id = ctx.get("job_id", "unknown")
    logger.info(f"Starting forecast job {job_id}")
    
    # 1. Trigger YOLO Camera Sampling & Inventory Sync (box_logs -> daily_inventories -> monthly_inventories)
    try:
        from sampling_worker.sampler import sample_camera_frames
        logger.info("Executing YOLO camera sampling & inventory sync before forecasting...")
        sample_res = await sample_camera_frames(crop=True, record_db=True)
        logger.info(
            "YOLO Sampling complete: ZoneA=%s, ZoneB=%s, Total=%s (bucket: %s)",
            sample_res.get("boxes_A"),
            sample_res.get("boxes_B"),
            sample_res.get("total_boxes"),
            sample_res.get("bucket"),
        )
    except Exception as e_samp:
        logger.warning("Camera sampling in forecast task failed: %s", e_samp, exc_info=True)

    # 2. Proceed with ARIMA Forecasting
    try:
        req = ForecastRequest(**req_data)
        async with SessionLocal() as session:
            service = ForecastingService(session)
            result = await service.run_forecast(req)
            logger.info(f"Forecast job {job_id} completed successfully")
            return result.model_dump()
    except Exception as e:
        logger.error(f"Forecast job {job_id} failed: {str(e)}", exc_info=True)
        return {"status": "error", "error": str(e)}

class WorkerSettings:
    """กำหนดคิวงานพยากรณ์ การเชื่อมต่อ Redis และข้อจำกัดการทำงานของ worker"""
    functions = [run_forecast_task]
    queue_name = "forecasting_queue"
    job_timeout = 300 # 5 minutes max
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://redis:6379"))
    max_jobs = 2
    poll_delay = 0.5
