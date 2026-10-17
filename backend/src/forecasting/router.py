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
    WhatIfSimulateRequest, WhatIfSimulateResponse,
)
from db.database import get_db_session
from models.stock import ArimaForecast, SarimaxForecast, ForecastResult, ExogenousDaily

router = APIRouter(prefix="/forecast", tags=["forecast"])

async def get_redis_pool():
    return await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))

@router.get("/latest", response_model=ForecastResponse)
async def get_latest_forecast(
    product: str,
    model_type: str = "total",
    session: AsyncSession = Depends(get_db_session)
):
    try:
        from datetime import timedelta
        # 1. Query SARIMAX table first (sarimax_forecasts)
        stmt_sarimax = (
            select(SarimaxForecast)
            .where(
                or_(SarimaxForecast.product == product, SarimaxForecast.product == "Frozen Shrimp"),
                SarimaxForecast.forecast_type == model_type,
            )
            .order_by(desc(SarimaxForecast.created_at), SarimaxForecast.time)
        )
        res_sarimax = await session.execute(stmt_sarimax)
        sarimax_records = res_sarimax.scalars().all()

        if sarimax_records:
            latest_time = sarimax_records[0].created_at
            cutoff = latest_time - timedelta(seconds=60)
            latest_s = [r for r in sarimax_records if r.created_at >= cutoff]
            latest_s.sort(key=lambda x: x.time)

            points = [
                ForecastDataPoint(
                    date=r.time,
                    predicted_value=int(round(r.predicted_value)),
                    lower_bound=max(0, int(round(r.lower_bound))) if r.lower_bound is not None else None,
                    upper_bound=max(0, int(round(r.upper_bound))) if r.upper_bound is not None else None,
                )
                for r in latest_s
            ]

            feature_importance = []
            if latest_s[0].feature_importance:
                try:
                    feature_importance = json.loads(latest_s[0].feature_importance)
                except Exception:
                    pass

            total_boxes = sum(p.predicted_value for p in points)
            lower_total = sum(p.lower_bound for p in points if p.lower_bound is not None)
            upper_total = sum(p.upper_bound for p in points if p.upper_bound is not None)
            financial_impact = {
                "total_predicted_boxes": total_boxes,
                "total_value_thb": round(total_boxes * 2200.0, 2),
                "lower_value_thb": round(lower_total * 2200.0, 2) if lower_total > 0 else None,
                "upper_value_thb": round(upper_total * 2200.0, 2) if upper_total > 0 else None,
                "estimated_holding_cost_monthly_thb": round(total_boxes * 45.0, 2),
                "price_per_kg_thb": 220.0,
                "price_per_box_thb": 2200.0,
                "holding_cost_per_box_thb": 45.0,
            }

            return ForecastResponse(
                product=product,
                model_name=latest_s[0].model_order or "SARIMAX",
                metrics=ForecastMetrics(),
                forecast=points,
                model_uri=f"sarimax_{product}_{model_type}",
                model_type=model_type,
                feature_importance=feature_importance,
                financial_impact=financial_impact,
                dual_summary={"model_type": model_type, "points": len(points)},
            )

        # 2. Query legacy table: arima_forecasts
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

            total_boxes = sum(p.predicted_value for p in points)
            lower_total = sum(p.lower_bound for p in points if p.lower_bound is not None)
            upper_total = sum(p.upper_bound for p in points if p.upper_bound is not None)
            financial_impact = {
                "total_predicted_boxes": total_boxes,
                "total_value_thb": round(total_boxes * 2200.0, 2),
                "lower_value_thb": round(lower_total * 2200.0, 2) if lower_total > 0 else None,
                "upper_value_thb": round(upper_total * 2200.0, 2) if upper_total > 0 else None,
                "estimated_holding_cost_monthly_thb": round(total_boxes * 45.0, 2),
                "price_per_kg_thb": 220.0,
                "price_per_box_thb": 2200.0,
                "holding_cost_per_box_thb": 45.0,
            }

            return ForecastResponse(
                product=product,
                model_name=latest_records[0].model_order or "ARIMA",
                metrics=metrics_obj,
                forecast=points,
                model_uri=model_uri,
                financial_impact=financial_impact,
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

        total_boxes = sum(p.predicted_value for p in points)
        lower_total = sum(p.lower_bound for p in points if p.lower_bound is not None)
        upper_total = sum(p.upper_bound for p in points if p.upper_bound is not None)
        financial_impact = {
            "total_predicted_boxes": total_boxes,
            "total_value_thb": round(total_boxes * 2200.0, 2),
            "lower_value_thb": round(lower_total * 2200.0, 2) if lower_total > 0 else None,
            "upper_value_thb": round(upper_total * 2200.0, 2) if upper_total > 0 else None,
            "estimated_holding_cost_monthly_thb": round(total_boxes * 45.0, 2),
            "price_per_kg_thb": 220.0,
            "price_per_box_thb": 2200.0,
            "holding_cost_per_box_thb": 45.0,
        }

        return ForecastResponse(
            product=product,
            model_name=latest_records_old[0].model_name or "ARIMA",
            metrics=ForecastMetrics(),
            forecast=points,
            model_uri=latest_records_old[0].model_version,
            financial_impact=financial_impact,
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


@router.get("/exogenous/latest")
async def get_latest_exogenous_data(session: AsyncSession = Depends(get_db_session)):
    """ดึงข้อมูลดัชนีภายนอกล่าสุด (สภาพอากาศ, ค่าเงิน, ค่าระวางเรือ, เทศกาล)"""
    try:
        from datetime import date, timedelta
        stmt = select(ExogenousDaily).order_by(desc(ExogenousDaily.date)).limit(1)
        res = await session.execute(stmt)
        record = res.scalar_one_or_none()

        if record:
            return {
                "date": str(record.date),
                "wind_speed_max_kmh": record.wind_speed_max_kmh,
                "is_storm": record.is_storm,
                "precipitation_mm": record.precipitation_mm,
                "sea_surface_temp_c": record.sea_surface_temp_c,
                "wave_height_m": record.wave_height_m,
                "usd_thb": record.usd_thb,
                "jpy_thb": record.jpy_thb,
                "eur_thb": record.eur_thb,
                "brent_crude_usd": record.brent_crude_usd,
                "tu_bk_close": record.tu_bk_close,
                "asian_bk_close": record.asian_bk_close,
                "is_fishing_ban": record.is_fishing_ban,
                "is_chinese_new_year": record.is_chinese_new_year,
                "is_songkran": record.is_songkran,
                "is_vegetarian_festival": record.is_vegetarian_festival,
                "is_christmas_newyear": record.is_christmas_newyear,
                "lunar_phase": record.lunar_phase,
                "source": record.source or "open-meteo+yfinance",
            }

        # Fallback live pull if DB is empty
        from data_worker.data_service import fetch_complete_exogenous_dataset
        today = date.today()
        df = await fetch_complete_exogenous_dataset(today - timedelta(days=3), today)
        latest_row = df.iloc[-1].to_dict()
        latest_row["date"] = str(latest_row["date"])
        return latest_row
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch exogenous indicators: {str(e)}")


@router.post("/simulate", response_model=WhatIfSimulateResponse)
async def simulate_what_if_scenario(
    req: WhatIfSimulateRequest,
    session: AsyncSession = Depends(get_db_session)
):
    """จำลองสถานการณ์ What-If บน SARIMAX (พายุ, ค่าเงินบาท, ช่วงปิดอ่าว) พร้อมผลกระทบทางการเงิน"""
    try:
        from inference_worker.forecast_model.service import ForecastingService

        service = ForecastingService(session)

        # 1. Run Baseline Forecast
        base_req = ForecastRequest(
            product=req.product,
            forecast_horizon=req.forecast_horizon,
            model_type="inbound",
            use_exog=True,
            storm_shock_days=0,
            fx_shock_pct=0.0,
        )
        base_res = await service.run_forecast(base_req)

        # 2. Run Simulated Shock Forecast
        sim_req = ForecastRequest(
            product=req.product,
            forecast_horizon=req.forecast_horizon,
            model_type="inbound",
            use_exog=True,
            storm_shock_days=req.storm_days,
            fx_shock_pct=req.fx_change_pct,
        )
        sim_res = await service.run_forecast(sim_req)

        base_total = sum(p.predicted_value for p in base_res.forecast)
        sim_total = sum(p.predicted_value for p in sim_res.forecast)
        delta_boxes = int(round(sim_total - base_total))
        delta_pct = round((delta_boxes / max(1.0, float(base_total))) * 100.0, 2)
        financial_impact = round(delta_boxes * 10.0 * req.price_per_kg_thb, 2)

        if delta_boxes < 0:
            rec = (
                f"เตือนภัย: คาดการณ์วัตถุดิบลดลง {abs(delta_boxes):,} กล่อง ({delta_pct}%) "
                f"กระทบมูลค่าการผลิต {abs(financial_impact):,.0f} บาท แนะนำให้ฝ่ายจัดซื้อจัดหาตุนวัตถุดิบล่วงหน้า "
                f"หรือขยาย Safety Stock รองรับคำสั่งซื้อ"
            )
        else:
            rec = (
                f"สภาวะเอื้ออำนวย: ปริมาณวัตถุดิบมีแนวโน้มเพิ่มขึ้น {delta_boxes:,} กล่อง (+{delta_pct}%) "
                f"เพิ่มมูลค่าสต็อกเข้าคลัง {financial_impact:,.0f} บาท แนะนำเตรียมแรงงานและพื้นที่ห้องเย็น"
            )

        return WhatIfSimulateResponse(
            baseline_forecast=base_res.forecast,
            simulated_forecast=sim_res.forecast,
            delta_boxes=delta_boxes,
            delta_percentage=delta_pct,
            financial_impact_thb=financial_impact,
            recommendation=rec,
            feature_impacts=sim_res.feature_importance or [],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"What-If simulation failed: {str(e)}")


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
