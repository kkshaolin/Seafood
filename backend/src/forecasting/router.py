"""Router สำหรับจัดคิว forecast jobs และ queryผลลัพธ์จากฐานข้อมูล.

ด้วย compose.yml backend service จะประกาศอุปกรณ์และ worker ให้ทำงานภายใต้ Redis queue
ดังนั้น endpoint เหล่านี้ใช้สำหรับส่งงาน forecasting และตรวจสอบสถานะของ job.
"""

import os
import re
import uuid
import json
from fastapi import APIRouter, Depends, HTTPException, status
from arq import create_pool
from arq.connections import RedisSettings
from arq.jobs import Job, JobStatus
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, or_

from core.config import settings
from forecasting.schemas import (
    ForecastRequest, ForecastJobResponse, ForecastJobStatusResponse,
    ForecastResponse, ForecastDataPoint, ForecastMetrics,
    YoloTrainRequest, TrainJobResponse,
)
from db.database import get_db_session
from models.stock import ArimaForecast, ForecastResult

router = APIRouter(prefix="/forecast", tags=["forecast"])

async def get_redis_pool():
    return await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))

@router.get("/latest", response_model=ForecastResponse)
async def get_latest_forecast(
    product: str,
    session: AsyncSession = Depends(get_db_session)
):
    try:
        from datetime import timedelta
        # 1. Query new table: arima_forecasts
        stmt = (
            select(ArimaForecast)
            .where(or_(ArimaForecast.product == product, ArimaForecast.product == "Frozen Shrimp"))
            .order_by(desc(ArimaForecast.created_at), ArimaForecast.time)
        )
        result = await session.execute(stmt)
        records = result.scalars().all()
        
        if records:
            latest_created_at = records[0].created_at
            cutoff = latest_created_at - timedelta(seconds=60)
            latest_records = [r for r in records if r.created_at >= cutoff]
            latest_records.sort(key=lambda x: x.time)
            points = [
                ForecastDataPoint(
                    date=r.time,
                    predicted_value=int(round(r.total_boxes)),
                    lower_bound=max(0, int(round(r.lower_bound))) if r.lower_bound is not None else None,
                    upper_bound=max(0, int(round(r.upper_bound))) if r.upper_bound is not None else None,
                )
                for r in latest_records
            ]
            metrics_obj = ForecastMetrics()
            model_uri = None
            try:
                import json
                from pathlib import Path
                storage_root = os.getenv("STORAGE_ROOT", "/app/storage")
                safe_product = re.sub(r"[^A-Za-z0-9_.-]", "_", product)
                m_path = Path(storage_root) / "models" / "time_serie" / f"arima_{safe_product}.json"
                if not m_path.exists() and product == "Premium_White_Shrimp":
                    m_path = Path(storage_root) / "models" / "time_serie" / "arima_premium_shrimp.json"
                if m_path.exists():
                    m_data = json.loads(m_path.read_text(encoding="utf-8"))
                    metrics_obj = ForecastMetrics(
                        mae=float(m_data["mae"]) if m_data.get("mae") is not None else None,
                        rmse=float(m_data["rmse"]) if m_data.get("rmse") is not None else None,
                        mape=float(m_data["mape"]) if m_data.get("mape") is not None else None,
                        aic=float(m_data["aic"]) if m_data.get("aic") is not None else None,
                        bic=float(m_data["bic"]) if m_data.get("bic") is not None else None,
                        baselines=m_data.get("baselines"),
                        evaluation_notes=m_data.get("evaluation_notes"),
                    )
                    model_uri = m_data.get("local_model_path")
            except Exception:
                pass

            return ForecastResponse(
                product=product,
                model_name=latest_records[0].model_order or "ARIMA",
                metrics=metrics_obj,
                forecast=points,
                model_uri=model_uri
            )

        # 2. Fallback to old table: forecast_results
        stmt_old = (
            select(ForecastResult)
            .where(or_(ForecastResult.product == product, ForecastResult.product == "Frozen Shrimp"))
            .order_by(desc(ForecastResult.created_at), ForecastResult.forecast_date)
        )
        result_old = await session.execute(stmt_old)
        records_old = result_old.scalars().all()
        
        if not records_old:
            raise HTTPException(status_code=404, detail="No forecast found for this product")
            
        latest_created_at = records_old[0].created_at
        cutoff = latest_created_at - timedelta(seconds=60)
        latest_records_old = [r for r in records_old if r.created_at >= cutoff]
        latest_records_old.sort(key=lambda x: x.forecast_date)
        points = [
            ForecastDataPoint(
                date=r.forecast_date,
                predicted_value=int(round(r.predicted_value)),
                lower_bound=max(0, int(round(r.lower_bound))) if r.lower_bound is not None else None,
                upper_bound=max(0, int(round(r.upper_bound))) if r.upper_bound is not None else None,
            )
            for r in latest_records_old
        ]
        return ForecastResponse(
            product=product,
            model_name=latest_records_old[0].model_name or "ARIMA",
            metrics=ForecastMetrics(),
            forecast=points,
            model_uri=latest_records_old[0].model_version
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("", response_model=ForecastJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def queue_arima_forecast(
    req: ForecastRequest,
    redis=Depends(get_redis_pool)
):
    try:
        job_id = str(uuid.uuid4())
        # Enqueue job to forecasting_queue
        await redis.enqueue_job(
            "run_forecast_task",
            req.model_dump(),
            _job_id=job_id,
            _queue_name="forecasting_queue"
        )
        return ForecastJobResponse(job_id=job_id, status="queued")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue forecast job: {str(e)}")

@router.post("/train", response_model=TrainJobResponse, status_code=status.HTTP_202_ACCEPTED,
             summary="เทรน ARIMA จาก PostgreSQL และบันทึกโมเดลขึ้น MinIO")
async def queue_arima_training(
    req: ForecastRequest,
    redis=Depends(get_redis_pool)
):
    """Enqueue ARIMA training job เข้า training_queue

    Worker จะดึงข้อมูลสต็อกจาก PostgreSQL (ไม่ใช่ CSV) และ camera_logs
    เพื่อใช้เป็น exogenous variable แล้วบันทึกโมเดล .pkl ขึ้น MinIO
    """
    try:
        job_id = str(uuid.uuid4())
        payload = req.model_dump()
        payload["model_type"] = "arima"   # บอก worker ว่าเป็น ARIMA
        await redis.enqueue_job(
            "run_training_task",
            payload,
            _job_id=job_id,
            _queue_name="training_queue"
        )
        return TrainJobResponse(job_id=job_id, status="queued", model_type="arima")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue ARIMA training job: {str(e)}")


@router.post("/train/yolo", response_model=TrainJobResponse, status_code=status.HTTP_202_ACCEPTED,
             summary="เทรน YOLO จาก Dataset ใน MinIO และบันทึกโมเดลขึ้น MinIO")
async def queue_yolo_training(
    req: YoloTrainRequest,
    redis=Depends(get_redis_pool)
):
    """Enqueue YOLO training job เข้า training_queue

    Worker จะดาวน์โหลด Dataset ZIP จาก MinIO bucket "datasets"
    ที่ key yolo/<dataset_name>/<dataset_name>.zip แล้วเทรน YOLO11n
    และอัปโหลด best.pt + metrics.json ขึ้น MinIO bucket "models"

    **ตัวอย่าง Request Body:**
    ```json
    {
      "dataset_name": "shrimp_v1",
      "class_names": ["shrimp"],
      "epochs": 20,
      "imgsz": 640,
      "batch": 8,
      "patience": 5
    }
    ```
    """
    try:
        job_id = str(uuid.uuid4())
        payload = req.model_dump()
        payload["model_type"] = "yolo"    # บอก worker ว่าเป็น YOLO
        await redis.enqueue_job(
            "run_training_task",
            payload,
            _job_id=job_id,
            _queue_name="training_queue"
        )
        return TrainJobResponse(job_id=job_id, status="queued", model_type="yolo")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue YOLO training job: {str(e)}")



@router.get("/{job_id}", response_model=ForecastJobStatusResponse)
async def get_forecast_job_status(
    job_id: str,
    redis=Depends(get_redis_pool)
):
    try:
        job = Job(job_id, redis, _queue_name="forecasting_queue")
        job_status = await job.status()
        
        if job_status == JobStatus.not_found:
            job = Job(job_id, redis, _queue_name="training_queue")
            job_status = await job.status()
            
        if job_status == JobStatus.not_found:
            raise HTTPException(status_code=404, detail="Job not found")
            
        status_str = "queued"
        result = None
        error = None
        sampling_progress = await redis.get(f"forecast:{job_id}:sampling")
        if isinstance(sampling_progress, bytes):
            sampling_progress = sampling_progress.decode("utf-8")
        sampling_data = json.loads(sampling_progress) if sampling_progress else {}

        if job_status == JobStatus.in_progress:
            status_str = "running"
        elif job_status == JobStatus.complete:
            status_str = "completed"

        # ตรวจสอบผลลัพธ์ผ่าน result_info() โดยไม่ trigger re-raise exception หากงานล้มเหลว
        res_info = await job.result_info()
        if res_info is not None:
            if not res_info.success:
                status_str = "failed"
                error = str(res_info.result) if res_info.result else "Job execution failed with exception"
                result = None
            else:
                job_result = res_info.result
                if isinstance(job_result, dict) and job_result.get("status") in ("error", "failed"):
                    status_str = "failed"
                    error = job_result.get("error") or "Job execution failed"
                    result = None
                else:
                    status_str = "completed"
                    result = job_result
                    if isinstance(job_result, dict):
                        sampling_data = {
                            "sampled_frames": job_result.get("sampled_frames"),
                            "sampled_detections": job_result.get("sampled_detections"),
                            "sampling_error": job_result.get("sampling_error"),
                        }
                
        return ForecastJobStatusResponse(
            status=status_str,
            result=result,
            error=error,
            sampled_frames=sampling_data.get("sampled_frames"),
            sampled_detections=sampling_data.get("sampled_detections"),
            sampling_error=sampling_data.get("sampling_error"),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
