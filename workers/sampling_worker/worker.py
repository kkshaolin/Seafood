"""Sampling Worker: ARQ worker for camera frame capturing and daily scheduled tasks.

Features:
1. On-demand sampling task: run_sampling_task (triggered when user clicks Predict on dashboard).
2. Daily automated schedule: scheduled_daily_sampling (runs daily at midnight, but disabled by default via DAILY_SAMPLING_ENABLED=false).
"""

import logging
import os
import sys

from arq import cron
from arq.connections import RedisSettings

# Ensure worker and backend paths are importable
workspace_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
backend_src = os.path.join(workspace_root, "backend", "src")
workers_src = os.path.join(workspace_root, "workers")
for _p in [backend_src, workers_src, workspace_root]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from sampling_worker.sampler import sample_camera_frames

logger = logging.getLogger("sampling_worker")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s"))
    logger.addHandler(_handler)


async def startup(ctx):
    daily_enabled = os.getenv("DAILY_SAMPLING_ENABLED", "false").lower() in ("true", "1", "yes")
    logger.info("Sampling Worker starting up... [Daily automated schedule: %s]", "ENABLED" if daily_enabled else "DISABLED (default)")


async def shutdown(ctx):
    logger.info("Sampling Worker shutting down...")


async def run_sampling_task(ctx, **kwargs) -> dict:
    """On-demand sampling task triggered via API or predict action."""
    job_id = ctx.get("job_id", "unknown")
    logger.info("Starting on-demand camera sampling task [job_id=%s]...", job_id)
    try:
        result = await sample_camera_frames(crop=True, record_db=True)
        logger.info("Camera sampling task completed successfully [job_id=%s]: ZoneA=%s, ZoneB=%s",
                    job_id, result.get("zone_a_key"), result.get("zone_b_key"))
        return result
    except Exception as e:
        logger.error("Camera sampling task failed [job_id=%s]: %s", job_id, e, exc_info=True)
        return {"status": "error", "error": str(e)}


async def scheduled_daily_sampling(ctx) -> dict:
    """Automated daily sampling cron job. Checks DAILY_SAMPLING_ENABLED before executing."""
    daily_enabled = os.getenv("DAILY_SAMPLING_ENABLED", "false").lower() in ("true", "1", "yes")
    if not daily_enabled:
        logger.info("Daily camera sampling skipped: DAILY_SAMPLING_ENABLED is currently disabled (OFF).")
        return {"status": "skipped", "reason": "DAILY_SAMPLING_ENABLED is disabled by configuration"}

    logger.info("Executing automated daily camera sampling...")
    try:
        result = await sample_camera_frames(crop=True, record_db=True)
        logger.info("Automated daily sampling finished successfully.")
        return result
    except Exception as e:
        logger.error("Automated daily sampling encountered an error: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}


class WorkerSettings:
    """ARQ Worker Settings for sampling_worker."""
    functions = [run_sampling_task, scheduled_daily_sampling]
    cron_jobs = [cron(scheduled_daily_sampling, hour=0, minute=0)]
    queue_name = "sampling_queue"
    job_timeout = 180
    max_jobs = 4
    poll_delay = 0.5
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://redis:6379"))
