"""
Inference Worker - รับผิดชอบเฉพาะการทำ Inference จาก Model ที่เทรนเสร็จแล้ว
"""
import os
import asyncio
import logging
import time
import mlflow.pyfunc
from arq.connections import RedisSettings

# --- OpenTelemetry Setup ---
from opentelemetry import trace, metrics
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.instrumentation.logging import LoggingInstrumentor

resource = Resource.create({"service.name": os.getenv("OTEL_SERVICE_NAME", "inference_worker")})

# Tracing
tracer_provider = TracerProvider(resource=resource)
otlp_trace_exporter = OTLPSpanExporter(
    endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel_collector:4317"), insecure=True
)
tracer_provider.add_span_processor(BatchSpanProcessor(otlp_trace_exporter))
trace.set_tracer_provider(tracer_provider)
tracer = trace.get_tracer(__name__)

# Metrics
otlp_metric_exporter = OTLPMetricExporter(
    endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel_collector:4317"), insecure=True
)
meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[PeriodicExportingMetricReader(otlp_metric_exporter)]
)
metrics.set_meter_provider(meter_provider)
meter = metrics.get_meter(__name__)

# Define Metrics
inference_counter = meter.create_counter("inference_requests_total", description="Total number of inference requests")
inference_success_counter = meter.create_counter("inference_success_total", description="Total number of successful inferences")
inference_error_counter = meter.create_counter("inference_error_total", description="Total number of failed inferences")
inference_duration = meter.create_histogram("inference_duration_seconds", description="Duration of inference tasks")

from cachetools import LRUCache
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import re

# --- OpenTelemetry Setup ---
# (Keeping existing OTel imports...)

# Define Metrics (Already defined in existing file)
# ดึง Trace ID และ Span ID จาก OpenTelemetry มาแนบใน Log อัตโนมัติเพื่อทำ Log Correlation
class TraceContextFilter(logging.Filter):
    def filter(self, record):
        try:
            from opentelemetry import trace
            ctx = trace.get_current_span().get_span_context()
            if ctx.is_valid:
                record.otelTraceID = trace.format_trace_id(ctx.trace_id)
                record.otelSpanID = trace.format_span_id(ctx.span_id)
            else:
                record.otelTraceID = "0"
                record.otelSpanID = "0"
        except ImportError:
            record.otelTraceID = "0"
            record.otelSpanID = "0"
        except Exception as e:
            record.otelTraceID = "0"
            record.otelSpanID = "0"
            import sys
            print(f"TraceContextFilter error: {e}", file=sys.stderr)
        return True

# ตั้งค่า Logging สำหรับ Inference Worker โดยเฉพาะ
handler = logging.StreamHandler()
handler.addFilter(TraceContextFilter())

class SafeOtelFormatter(logging.Formatter):
    def format(self, record):
        if not hasattr(record, 'otelTraceID'):
            record.otelTraceID = "0"
        if not hasattr(record, 'otelSpanID'):
            record.otelSpanID = "0"
        return super().format(record)

formatter = SafeOtelFormatter(
    fmt="%(asctime)s | %(levelname)-8s | trace_id=%(otelTraceID)s span_id=%(otelSpanID)s | inference_worker | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
handler.setFormatter(formatter)

# Configure root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
for h in root_logger.handlers[:]:
    root_logger.removeHandler(h)
root_logger.addHandler(handler)

logger = logging.getLogger("inference_worker")

from collections import defaultdict

# จำกัดขนาด Cache และสร้าง Lock เพื่อป้องกัน OOM และ Concurrency Issues
model_cache = LRUCache(maxsize=3)
model_load_locks = defaultdict(asyncio.Lock) # ล็อกการโหลดโมเดล ป้องกันหลาย Request โหลดซ้ำ (Thundering Herd)
model_predict_locks = defaultdict(asyncio.Lock) # ล็อกการทำนายผล ป้องกันปัญหา Thread-Safety ใน ML Libraries

# ตั้งค่า MLflow tracking URI เป็นตัวแปร Global
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)

from opentelemetry.propagate import extract

async def startup(ctx):
    """ฟังก์ชันทำงานเมื่อ Worker เริ่มต้น"""
    logger.info("Inference Worker starting up...")
    ctx["start_time"] = asyncio.get_event_loop().time()

async def shutdown(ctx):
    """ฟังก์ชันทำงานเมื่อ Worker ปิดตัว"""
    logger.info("Inference Worker shutting down...")
    model_cache.clear()
    model_load_locks.clear()
    model_predict_locks.clear()
    logger.info("Cleared model cache and locks.")

# โหลดโมเดลจาก MLflow แบบมี Retry ลดผลกระทบจาก Network ขัดข้องชั่วคราว
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True
)
def _load_model_sync(model_uri: str):
    """โหลดโมเดลแบบ Synchronous พร้อม Retry"""
    logger.info(f"Attempting to load model from MLflow: {model_uri}")
    return mlflow.pyfunc.load_model(model_uri)

def _predict_sync(model, input_data):
    """ฟังก์ชันรัน Prediction สไตล์ Synchronous (เพื่อเอาไปรันใน Thread)"""
    return model.predict(input_data)

async def inference_task(ctx, model_uri: str, input_data: list, carrier: dict = None) -> dict:
    """Inference task that loads a model from MLflow and makes predictions."""
    job_id = ctx.get("job_id", "unknown")
    start_time = time.time()
    
    otel_context = extract(carrier) if carrier else None
    
    with tracer.start_as_current_span("inference_workflow", context=otel_context) as workflow_span:
        workflow_span.set_attribute("job.id", job_id)
        workflow_span.set_attribute("model.uri", model_uri)
        workflow_span.set_attribute("input.size", len(input_data))
        
        inference_counter.add(1, {"model_uri": model_uri})
        logger.info(f"Prediction started for job {job_id}, model: {model_uri}")
        
        # ตรวจสอบรูปแบบ URI เพื่อป้องกันช่องโหว่ SSRF และ Path Traversal
        if ".." in model_uri or not re.match(r"^(models:/|runs:/|s3://|mlflow-artifacts:/)[a-zA-Z0-9_\-\./:]+$", model_uri):
            err_msg = f"Invalid model_uri format '{model_uri}'. Security violation."
            logger.error(err_msg)
            workflow_span.record_exception(ValueError(err_msg))
            inference_error_counter.add(1, {"model_uri": "invalid", "stage": "validation"})
            return {"status": "error", "error": err_msg}
        
        # โหลดโมเดล
        with tracer.start_as_current_span("load_model") as load_span:
            async with model_load_locks[model_uri]:
                if model_uri not in model_cache:
                    logger.info(f"Model not in cache, Model loading from MLflow: {model_uri}")
                    try:
                        # โหลดโมเดลใน Thread แยก เพื่อไม่ให้บล็อก Async Event Loop
                        model = await asyncio.to_thread(_load_model_sync, model_uri)
                        model_cache[model_uri] = model
                        logger.info("Model loaded successfully.")
                        load_span.set_attribute("cache.hit", False)
                    except Exception as e:
                        logger.error(f"Failed to load model after retries: {e}", exc_info=True)
                        load_span.record_exception(e)
                        workflow_span.record_exception(e)
                        inference_error_counter.add(1, {"model_uri": model_uri, "stage": "load"})
                        return {"status": "error", "error": f"Model load failed: {str(e)}"}
                else:
                    logger.info(f"Using cached model for {model_uri}")
                    model = model_cache[model_uri]
                    load_span.set_attribute("cache.hit", True)
        
        # ทำการพยากรณ์
        with tracer.start_as_current_span("model_predict") as predict_span:
            try:
                logger.info("Prediction running...")
                async with model_predict_locks[model_uri]:
                    # รันการทำนายผล (CPU-bound) ใน Thread แยก
                    predictions = await asyncio.to_thread(_predict_sync, model, input_data)
                
                # Post-processing
                if hasattr(predictions, "tolist"):
                    predictions = predictions.tolist()
                    
                logger.info("Prediction completed successfully.")
                
                duration = time.time() - start_time
                inference_duration.record(duration, {"model_uri": model_uri})
                inference_success_counter.add(1, {"model_uri": model_uri})
                
                return {
                    "status": "success",
                    "model_uri": model_uri,
                    "predictions": predictions
                }
            except Exception as e:
                logger.error(f"Prediction failed: {e}", exc_info=True)
                predict_span.record_exception(e)
                workflow_span.record_exception(e)
                inference_error_counter.add(1, {"model_uri": model_uri, "stage": "predict"})
                return {"status": "error", "error": str(e)}

class WorkerSettings:
    """การตั้งค่าสำหรับ Inference Worker โดยเฉพาะ"""
    # ลงทะเบียนฟังก์ชันเฉพาะ inference ห้ามมี train_model
    functions = [inference_task]
    
    # ระบุ queue_name เป็น inference_queue
    queue_name = "inference_queue"
    
    # กำหนด Timeout สูงสุดสำหรับ 1 Job (ป้องกัน Worker ค้าง)
    job_timeout = 50
    
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://redis:6379"))
    max_jobs = 10
    poll_delay = 0.5

if __name__ == "__main__":
    print("Run inference worker using: arq workers.inference_worker.WorkerSettings")
