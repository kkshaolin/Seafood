import os
import sys
import logging
from arq.connections import RedisSettings

# Setup paths to import backend modules
workspace_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
backend_src = os.path.join(workspace_root, "backend", "src")
if backend_src not in sys.path:
    sys.path.insert(0, backend_src)

from db.database import SessionLocal
from forecast_model.service import ForecastingService
from forecasting.schemas import ForecastRequest

logger = logging.getLogger("forecasting_worker")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

async def startup(ctx):
    logger.info("Forecasting Worker starting up...")

async def shutdown(ctx):
    logger.info("Forecasting Worker shutting down...")

async def run_forecast_task(ctx, req_data: dict) -> dict:
    """
    ARQ Job Function: ประมวลผล ARIMAX Forecasting
    """
    job_id = ctx.get("job_id", "unknown")
    logger.info(f"Starting forecast job {job_id}")
    
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
    """การตั้งค่าสำหรับ Forecasting Worker"""
    functions = [run_forecast_task]
    queue_name = "forecasting_queue"
    job_timeout = 300 # 5 minutes max
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://redis:6379"))
    max_jobs = 2
    poll_delay = 0.5
