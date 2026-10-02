"""Training Worker: ARQ entry point สำหรับ training jobs ทั้ง ARIMA และ YOLO

Compose เปิด service นี้ด้วย ``training_worker.worker.WorkerSettings``
บน queue ``training_queue``

งานแต่ละชิ้นรับ dict ที่มี field:
    model_type  : "arima" | "yolo"
    ...          : พารามิเตอร์เฉพาะโมเดล (ดู schema แต่ละ type)

ARIMA task schema:
    {
        "model_type": "arima",
        "product": str,                     # ชื่อสินค้า เช่น "Premium_White_Shrimp"
        "p": int  (default 1),
        "d": int  (default 1),
        "q": int  (default 1),
        "forecast_horizon": int (default 3),
        "warehouse": str | null (optional)
    }

YOLO task schema:
    {
        "model_type": "yolo",
        "dataset_name": str,                # ชื่อ dataset ใน MinIO bucket "datasets"
        "class_names": list[str] | null,    # default ["shrimp"]
        "epochs": int         (default 10),
        "imgsz": int          (default 640),
        "batch": int          (default 8),
        "patience": int       (default 5)
    }
"""
import logging
import os
import sys

from arq.connections import RedisSettings

# ---------------------------------------------------------------------------
# sys.path setup สำหรับ import backend schemas/models ร่วมกัน
# (เหมือนกับที่ inference_worker ทำ)
# ---------------------------------------------------------------------------
workspace_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
backend_src = os.path.join(workspace_root, "backend", "src")
inference_src = os.path.join(workspace_root, "workers", "inference_worker")
for _p in [backend_src, inference_src, workspace_root]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------
logger = logging.getLogger("training_worker")
logger.setLevel(logging.INFO)
_handler = logging.StreamHandler()
_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s"))
logger.addHandler(_handler)


# ---------------------------------------------------------------------------
# ARQ lifecycle hooks
# ---------------------------------------------------------------------------

async def startup(ctx):
    """บันทึกข้อความเมื่อ ARQ เริ่ม worker ฝึกโมเดล"""
    logger.info("Training Worker starting up... (supports: arima, yolo)")


async def shutdown(ctx):
    """บันทึกข้อความเมื่อ ARQ ปิด worker ฝึกโมเดล"""
    logger.info("Training Worker shutting down...")


# ---------------------------------------------------------------------------
# Main Task: Dispatcher
# ---------------------------------------------------------------------------

async def run_training_task(ctx, req_data: dict) -> dict:
    """
    รับ training request และ dispatch ไปยัง trainer ที่เหมาะสม

    จาก ``model_type`` ใน req_data:
        "arima"  →  trainers.arima_trainer.train_arima_model()
        "yolo"   →  trainers.yolo_trainer.train_yolo_model()

    คืน dict สรุปผลหรือ error พร้อม status field
    """
    job_id = ctx.get("job_id", "unknown")
    model_type = req_data.get("model_type", "arima").lower()
    logger.info("Training job %s started — model_type=%s", job_id, model_type)

    try:
        if model_type == "arima":
            from training_worker.trainers.arima_trainer import train_arima_model
            result = await train_arima_model(
                job_id=job_id,
                product=req_data.get("product", "Premium_White_Shrimp"),
                p=int(req_data.get("p", 1)),
                d=int(req_data.get("d", 1)),
                q=int(req_data.get("q", 1)),
                forecast_horizon=int(req_data.get("forecast_horizon", 3)),
                warehouse=req_data.get("warehouse"),
            )

        elif model_type == "yolo":
            from training_worker.trainers.yolo_trainer import train_yolo_model
            result = await train_yolo_model(
                job_id=job_id,
                dataset_name=req_data.get("dataset_name", "shrimp_v1"),
                class_names=req_data.get("class_names"),        # None → default ["shrimp"]
                epochs=int(req_data.get("epochs", 10)),
                imgsz=int(req_data.get("imgsz", 640)),
                batch=int(req_data.get("batch", 8)),
                patience=int(req_data.get("patience", 5)),
            )

        else:
            raise ValueError(
                f"model_type '{model_type}' ไม่รองรับ — ใช้ 'arima' หรือ 'yolo'"
            )

        logger.info("Training job %s completed successfully — model_type=%s", job_id, model_type)
        return result

    except Exception as e:
        logger.error("Training job %s failed: %s", job_id, str(e), exc_info=True)
        return {"status": "error", "model_type": model_type, "job_id": job_id, "error": str(e)}


# ---------------------------------------------------------------------------
# ARQ WorkerSettings
# ---------------------------------------------------------------------------

class WorkerSettings:
    """กำหนดคิวฝึกโมเดล การเชื่อมต่อ Redis และขีดจำกัดงานพร้อมกัน

    job_timeout ตั้งไว้ที่ 3600 วินาที (1 ชั่วโมง) เพื่อรองรับ YOLO training
    ที่ต้องใช้เวลานานกว่า ARIMA
    """
    functions = [run_training_task]
    queue_name = "training_queue"
    job_timeout = 3600          # 1 ชั่วโมง: ARIMA เร็วกว่ามาก แต่ YOLO ต้องการเวลา
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://redis:6379"))
    max_jobs = 1                # จำกัด 1 งานต่อครั้งเพราะ training ใช้ RAM สูง
    poll_delay = 0.5
