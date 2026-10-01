import os
import sys
import logging
from arq.connections import RedisSettings

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
    logger.info("Training Worker starting up...")

async def shutdown(ctx):
    logger.info("Training Worker shutting down...")

async def run_training_task(ctx, req_data: dict) -> dict:
    """
    ARQ Job Function: Train ARIMA Model
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
    functions = [run_training_task]
    queue_name = "training_queue" # Share the same queue for simplicity or use training_queue
    job_timeout = 600 # 10 minutes max
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://redis:6379"))
    max_jobs = 1
    poll_delay = 0.5
