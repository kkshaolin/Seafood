"""โมดูลหลักของ FastAPI backend สำหรับบริการสต็อกและการพยากรณ์สินค้า.

ไฟล์นี้ใช้เป็น entry point ของ backend service ใน compose.yml และกำหนด lifespan, OpenTelemetry,
CORS, health check รวมถึงการ mount router หลักที่ใช้งานจริง: stock, forecast, settings, risk.
"""

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
from services.storage import storage_service
from utils.logger import get_logger

from pydantic import BaseModel
from arq import create_pool
from arq.connections import RedisSettings
from datetime import datetime, timedelta
import json
import logging
import os

# ส่วนตั้งค่า OpenTelemetry: ใช้ติดตาม trace, metric และ log ของ FastAPI เพื่อช่วยดูสภาพแอปจริงใน production
# บล็อกนี้ทำให้ระบบสามารถบันทึก tracing และ metrics ของ FastAPI เพื่อติดตามเวลาและสถานะการทำงานของ endpoint
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
from fastapi import Response

resource = Resource.create({"service.name": os.getenv("OTEL_SERVICE_NAME", "fastapi_backend")})

# ส่วน tracing: บันทึกแต่ละ request ว่าเริ่มและสิ้นสุดที่ไหน เพื่อช่วยระบุจุดที่ทำงานช้า
tracer_provider = TracerProvider(resource=resource)
otlp_trace_exporter = OTLPSpanExporter(
    endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel_collector:4317"), insecure=True
)
tracer_provider.add_span_processor(BatchSpanProcessor(otlp_trace_exporter))
trace.set_tracer_provider(tracer_provider)

# ส่วน metrics: เก็บตัวชี้วัดเชิงสถิติ เช่น จำนวน request, latency และ error rate เพื่อใช้สังเกตระบบ
otlp_metric_exporter = OTLPMetricExporter(
    endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel_collector:4317"), insecure=True
)
meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[PeriodicExportingMetricReader(otlp_metric_exporter)]
)
metrics.set_meter_provider(meter_provider)

# เครื่องมือนี้จะผนวก trace_id และ span_id เข้าไปใน log เพื่อให้ค้นหาต้นเหตุได้ง่ายขึ้นเมื่อมีปัญหา
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
    
    # สร้าง connection pool ของ Redis เพื่อให้ worker และ queue สามารถส่งงานและเรียกงานต่อได้
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
    
    # ปิด connection pool เมื่อ backend shutdown เพื่อคืนทรัพยากร Redis ให้กับระบบอย่างเหมาะสม
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

# ติดตั้ง FastAPI Instrumentor ของ OpenTelemetry เพื่อเก็บ metrics และ trace ของ request ให้ระบบตรวจสอบประสิทธิภาพได้
FastAPIInstrumentor.instrument_app(app)

# ส่วน CORS: อนุญาตให้ frontend ที่เข้ามาจาก localhost ต่าง ๆ ติดต่อกับ API ได้อย่างปลอดภัย
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Router หลักที่ใช้งานจริงใน compose.yml คือ stock, forecast, camera, sampling, settings, risk และ huggingface
from api.stock.router import router as stock_router
app.include_router(stock_router, prefix="/api")
from forecasting.router import router as forecast_router
app.include_router(forecast_router, prefix="/api")
from api.settings import router as settings_router
app.include_router(settings_router, prefix="/api")
from api.risk import router as risk_router
app.include_router(risk_router, prefix="/api")
from api.sampling import router as sampling_router
app.include_router(sampling_router, prefix="/api")
from api.camera import router as camera_router
app.include_router(camera_router, prefix="/api")
from api.huggingface_router import router as hf_router
app.include_router(hf_router, prefix="/api")

@app.get("/health/live", tags=["system"], summary="Liveness Probe")
async def liveness_probe() -> dict:
    """Lightweight probe verifying process is responsive."""
    return {"status": "alive", "timestamp": datetime.utcnow().isoformat()}


@app.get("/health/ready", tags=["system"], summary="Readiness Probe")
async def readiness_probe(session: AsyncSession = Depends(get_db_session)) -> dict:
    """Readiness probe checking Postgres, Redis, and MinIO. Returns 503 if degraded."""
    from fastapi import status as http_status
    from fastapi.responses import JSONResponse

    res = await health_check(session=session)
    if res.get("status") != "healthy":
        return JSONResponse(status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE, content=res)
    return res


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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=True)