import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis
from redis import Redis

from core.config import settings
from db.database import create_database_schema, get_db_session
from api.auth.router import router as auth_router
from api.users.router import router as users_router
from api.storage.router import router as storage_router
from services.storage import storage_service
from utils.logger import get_logger

from pydantic import BaseModel
from arq import create_pool
from arq.connections import RedisSettings
from datetime import datetime, timedelta
import json
import logging
import os

# --- OpenTelemetry Setup ---
from opentelemetry import trace, metrics
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor

resource = Resource.create({"service.name": os.getenv("OTEL_SERVICE_NAME", "fastapi_backend")})

# Tracing
tracer_provider = TracerProvider(resource=resource)
otlp_trace_exporter = OTLPSpanExporter(
    endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel_collector:4317"), insecure=True
)
tracer_provider.add_span_processor(BatchSpanProcessor(otlp_trace_exporter))
trace.set_tracer_provider(tracer_provider)

# Metrics
otlp_metric_exporter = OTLPMetricExporter(
    endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel_collector:4317"), insecure=True
)
meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[PeriodicExportingMetricReader(otlp_metric_exporter)]
)
metrics.set_meter_provider(meter_provider)

# Logging Instrumentor injects trace_id and span_id into log records
LoggingInstrumentor().instrument(set_logging_format=False)
# -----------------------------

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
logger = get_logger("backend_main")


API_DESCRIPTION = """
**AI Ecosystem Backend Server APIs**

ระบบบริการสำหรับสถาปัตยกรรม **AI Engineering Ecosystem** แบบครบวงจร 

---

### ส่วนประกอบและบริการของระบบ (System Components)
**Auth & User Services**: ระบบลงทะเบียน ยืนยันตัวตนผ่าน JWT Token และการจัดการผู้ใช้
**Storage Services**: ระบบจัดการอัปโหลดไฟล์ Dataset และสื่อเข้า MinIO Object Storage
**Worker Task Services**: สั่งงานประมวลผลโมเดล AI / Data Ingestion เข้า Redis Queue (ARQ)
**Health Check Services**: ตรวจสอบสถานะการเชื่อมต่อบริการ PostgreSQL, Redis และ MinIO
"""

OPENAPI_TAGS = [
    {
        "name": "system",
        "description": "ระบบตรวจสอบสถานะความพร้อมและการเชื่อมต่อบริการรองรับทั้งหมด (Health Check & Diagnostics)",
    },
    {
        "name": "auth",
        "description": "ระบบการยืนยันตัวตน สมัครสมาชิก และออก JWT Access Token สำหรับเข้าใช้งาน",
    },
    {
        "name": "users",
        "description": "ระบบจัดการข้อมูลผู้ใช้งาน (User Management CRUD)",
    },
    {
        "name": "storage",
        "description": "ระบบอัปโหลดไฟล์ Dataset และภาพเข้า MinIO Object Storage พร้อมส่งงานเข้า Background Worker Queue",
    },
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} in environment '{settings.APP_ENV}'...")
    
    # Initialize ARQ Redis Pool
    try:
        app.state.redis_pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
        logger.info("ARQ Redis pool initialized.")
    except Exception as e:
        logger.error(f"Failed to initialize ARQ Redis pool: {e}")

    try:
        await create_database_schema()
        logger.info("Database schema initialized successfully.")
    except Exception as e:
        logger.warning(f"Database schema initialization skipped or failed: {e}")
    
    yield
    
    # Close ARQ Redis Pool
    if hasattr(app.state, 'redis_pool'):
        await app.state.redis_pool.close()
    logger.info(f"Shutting down {settings.APP_NAME}...")


app = FastAPI(
    title=f"{settings.APP_NAME} - AI Ecosystem APIs",
    description=API_DESCRIPTION,
    version="1.0.0",
    terms_of_service="http://localhost:8000/terms",
    contact={
        "name": "AI Ecosystem Student Team",
        "url": "http://localhost:8000",
        "email": "student@example.com",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
    openapi_tags=OPENAPI_TAGS,
    debug=settings.DEBUG,
    lifespan=lifespan,
    docs_url="/",
    redoc_url="/redoc",
)

# ติดตั้ง OTel FastAPI Instrumentor เพื่อเก็บ Metrics และ Traces
FastAPIInstrumentor.instrument_app(app)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Include Routers
app.include_router(auth_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(storage_router, prefix="/api")

class TrainingRequest(BaseModel):
    dataset_name: str
    model_name: str = "distilbert-base-uncased"
    scheduled_time: str | None = None  # ISO format: "2024-01-01T10:00:00"
    epochs: int = 3
    batch_size: int = 16
    
@app.get("/health", tags=["system"], summary="Comprehensive System Health Check")
async def health_check(session: AsyncSession = Depends(get_db_session)) -> dict:
    """Comprehensive health check endpoint checking Postgres, Redis, and MinIO services."""
    health_status = {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "services": {
            "database": "unknown",
            "redis": "unknown",
            "minio": "unknown",
        },
    }

    # 1. Check PostgreSQL
    try:
        await session.execute(text("SELECT 1"))
        health_status["services"]["database"] = "connected"
    except Exception as e:
        health_status["services"]["database"] = f"error: {str(e)}"
        health_status["status"] = "degraded"

    # 2. Check Redis
    try:
        r = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
        health_status["services"]["redis"] = "connected"
    except Exception as e:
        health_status["services"]["redis"] = f"error: {str(e)}"
        health_status["status"] = "degraded"

    # 3. Check MinIO
    if storage_service.is_healthy():
        health_status["services"]["minio"] = "connected"
    else:
        health_status["services"]["minio"] = "error: unreachable"
        health_status["status"] = "degraded"

    return health_status

from fastapi import Request
from arq.jobs import Job

@app.post("/add_train_queue_time")
async def add_train_queue(request_data: TrainingRequest, request: Request):
    """
    เพิ่ม job เข้าคิวฝึกโมเดล สามารถกำหนดเวลาเริ่มได้
    """
    job_id = f"train_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    job_data = {
        "job_id": job_id,
        "dataset_name": request_data.dataset_name,
        "model_name": request_data.model_name,
        "epochs": request_data.epochs,
        "batch_size": request_data.batch_size,
        "created_at": datetime.now().isoformat()
    }
    
    redis_pool = request.app.state.redis_pool
    
    if request_data.scheduled_time:
        # Schedule for future execution
        schedule_time = datetime.fromisoformat(request_data.scheduled_time)
        job = await redis_pool.enqueue_job(
            'train_model',
            job_data,
            _job_id=job_id,
            _defer_until=schedule_time,
            _queue_name="training_queue"
        )
        logger.info(f"Scheduled job {job_id} at {schedule_time}")
        return {
            "status": "scheduled",
            "job_id": job_id,
            "scheduled_time": request_data.scheduled_time,
            "message": f"Job will start at {schedule_time}"
        }
    else:
        # Enqueue immediately
        job = await redis_pool.enqueue_job(
            'train_model',
            job_data,
            _job_id=job_id,
            _queue_name="training_queue"
        )
        logger.info(f"Enqueued job {job_id}")
        return {
            "status": "queued",
            "job_id": job_id,
            "message": "Job added to queue"
        }

@app.get("/job_status/{job_id}")
async def get_job_status(job_id: str, request: Request):
    """ตรวจสอบสถานะ job"""
    redis_pool = request.app.state.redis_pool
    
    queue_name = "arq:queue"
    if job_id.startswith("train_"):
        queue_name = "training_queue"
    elif job_id.startswith("infer_"):
        queue_name = "inference_queue"
        
    job = Job(job_id, redis_pool, _queue_name=queue_name)
    status = await job.status()
    if status.value != "not_found":
        info = await job.info()
        return {
            "job_id": job_id,
            "status": status.value,
            "created_at": info.enqueue_time.isoformat() if info and hasattr(info, 'enqueue_time') else None,
            "result": await job.result(timeout=0) if status.value == "complete" else None
        }
    raise HTTPException(status_code=404, detail="Job not found")

from api.predict.router import router as predict_router
app.include_router(predict_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=True)