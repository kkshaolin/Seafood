"""ARQ Data Worker for periodic exogenous market & weather ingestion."""
from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from arq.connections import RedisSettings

from data_worker.data_service import sync_exogenous_to_database

logger = logging.getLogger("data_worker")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s"))
    logger.addHandler(_handler)


async def startup(ctx):
    logger.info("Data Worker starting up (Exogenous Data Pipeline)...")


async def shutdown(ctx):
    logger.info("Data Worker shutting down...")


async def run_data_ingestion_task(ctx, req_data: dict = None) -> dict:
    """Fetch recent weather, forex, and calendar features and sync to database."""
    req_data = req_data or {}
    days_back = req_data.get("days_back", 30)
    days_forward = req_data.get("days_forward", 14)

    today = date.today()
    start_date = today - timedelta(days=days_back)
    end_date = today + timedelta(days=days_forward)

    logger.info("Running exogenous data ingestion from %s to %s", start_date, end_date)
    count = await sync_exogenous_to_database(start_date, end_date)
    return {
        "status": "success",
        "start_date": str(start_date),
        "end_date": str(end_date),
        "records_synced": count,
    }


class WorkerSettings:
    """Configuration for ARQ data_worker service."""
    functions = [run_data_ingestion_task]
    queue_name = "data_queue"
    job_timeout = 300
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://redis:6379"))
    max_jobs = 2
    poll_delay = 1.0
