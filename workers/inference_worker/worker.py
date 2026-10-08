"""จุดเริ่มต้น ARQ สำหรับประมวลผลคำขอพยากรณ์

Compose เปิดโมดูลนี้เป็น ``forecasting-worker`` ด้วย
``inference_worker.worker.WorkerSettings`` ซึ่งรับงานจากคิว ``forecasting_queue``.
ตัว worker เตรียม path สำหรับ backend, เปิด session ฐานข้อมูลต่อ job
แล้วส่งคำขอที่ตรวจรูปแบบแล้วให้ ForecastingService ประมวลผลและบันทึกผล
"""
import os
import sys
import logging
import json
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
    
    # 1. Step 1: Trigger Camera Sampling (store raw frame in MinIO 'sampling-camera')
    #    Step 2: Inference Worker pulls from 'sampling-camera', detects with YOLO,
    #            stores annotated frames to 'result-yolo', and records both cameras to PostgreSQL.
    yolo_res = None
    sampling_error = None
    try:
        from sampling_worker.sampler import sample_camera_frames
        logger.info("Sampling raw camera frames into MinIO 'sampling-camera'...")
        sample_res = await sample_camera_frames(
            crop=True,
            video_time=req_data.get("video_time"),
            video_time_a=req_data.get("video_time_a"),
            video_time_b=req_data.get("video_time_b"),
            predict_timestamp=req_data.get("timestamp") or req_data.get("predict_timestamp"),
        )
        logger.info(
            "Raw frames sampled to '%s': ZoneA=%s, ZoneB=%s",
            sample_res.get("bucket"),
            sample_res.get("zone_a_key"),
            sample_res.get("zone_b_key"),
        )

        from inference_worker.yolo_inference_worker import run_yolo_detection_from_sampling
        logger.info("Inference Worker pulling latest frames from 'sampling-camera' to run YOLO detection...")
        yolo_res = await run_yolo_detection_from_sampling(
            zone_a_key=sample_res.get("zone_a_key"),
            zone_b_key=sample_res.get("zone_b_key"),
            record_db=True,
        )
        logger.info(
            "YOLO Detection complete: ZoneA=%s, ZoneB=%s, Total=%s (result bucket: %s)",
            yolo_res.get("boxes_A"),
            yolo_res.get("boxes_B"),
            yolo_res.get("total_boxes"),
            yolo_res.get("result_bucket"),
        )

        sampling_progress = {
            "sampled_frames": {
                "cam_main": yolo_res["zone_a_key"],
                "cam_dock": yolo_res["zone_b_key"],
            },
            "sampled_detections": {
                "cam_main": yolo_res["boxes_A"],
                "cam_dock": yolo_res["boxes_B"],
            },
        }
        try:
            await ctx["redis"].set(
                f"forecast:{job_id}:sampling",
                json.dumps(sampling_progress),
                ex=3600,
            )
        except Exception:
            logger.warning("Could not publish sampling progress for job %s", job_id, exc_info=True)
    except Exception as e_samp:
        logger.warning("Camera sampling / YOLO detection in forecast task failed: %s", e_samp, exc_info=True)
        sampling_error = str(e_samp)

    # 2. Proceed with ARIMA Forecasting
    try:
        req = ForecastRequest(**req_data)
        async with SessionLocal() as session:
            service = ForecastingService(session)
            result = await service.run_forecast(req)
            logger.info(f"Forecast job {job_id} completed successfully")
            response = result.model_dump()
            if yolo_res is not None:
                response["sampled_frames"] = {
                    "cam_main": yolo_res["zone_a_key"],
                    "cam_dock": yolo_res["zone_b_key"],
                }
                response["sampled_detections"] = {
                    "cam_main": yolo_res["boxes_A"],
                    "cam_dock": yolo_res["boxes_B"],
                }
            if sampling_error is not None:
                response["sampling_error"] = sampling_error
            return response
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
