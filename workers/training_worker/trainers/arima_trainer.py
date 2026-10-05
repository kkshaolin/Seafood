"""ARIMA Trainer: ดึงข้อมูลจาก PostgreSQL → เทรน → อัปโหลดโมเดล + metrics ขึ้น MinIO

Flow:
    1. ดึง inventory_summaries จาก PostgreSQL (แทน CSV เดิม)
    2. ดึง camera_logs (detected_count) เพื่อใช้เป็น exogenous variable
    3. เทรน ARIMA ด้วย chronological split → คำนวณ MAE/RMSE/MAPE
    4. เทรนโมเดลเต็มชุด → serialize เป็น .pkl
    5. อัปโหลดไฟล์โมเดลขึ้น MinIO bucket "models" ที่ key  arima/<product>/<job_id>/model.pkl
    6. คืน dict สรุปผลและ MinIO object key
"""
from __future__ import annotations

import io
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from minio import Minio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy import text

from inventory_data import get_inventory_csv_path, get_local_arima_model_path, load_inventory_time_series

logger = logging.getLogger("training_worker.arima")


# ---------------------------------------------------------------------------
# MinIO helpers
# ---------------------------------------------------------------------------

def _get_minio_client() -> Minio:
    """สร้าง MinIO client จาก environment variables."""
    return Minio(
        endpoint=os.getenv("MINIO_ENDPOINT", "minio:9000"),
        access_key=os.getenv("MINIO_ACCESS_KEY", "admin"),
        secret_key=os.getenv("MINIO_SECRET_KEY", "password123"),
        secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
    )


def _ensure_bucket(client: Minio, bucket: str) -> None:
    """สร้าง bucket ถ้ายังไม่มี."""
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
        logger.info("Created MinIO bucket: %s", bucket)


def _upload_bytes(client: Minio, bucket: str, key: str, data: bytes,
                  content_type: str = "application/octet-stream") -> str:
    """อัปโหลด bytes ขึ้น MinIO และคืน object key."""
    _ensure_bucket(client, bucket)
    client.put_object(
        bucket_name=bucket,
        object_name=key,
        data=io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    logger.info("Uploaded to MinIO: %s/%s (%d bytes)", bucket, key, len(data))
    return key


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _make_session_factory(database_url: str):
    """สร้าง async session factory และ engine จาก DATABASE_URL โดยใช้ NullPool."""
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif not database_url.startswith("postgresql+asyncpg://"):
        raise ValueError("DATABASE_URL must use a PostgreSQL URL scheme")
    engine = create_async_engine(database_url, poolclass=NullPool)
    return async_sessionmaker(engine, expire_on_commit=False), engine


async def _fetch_inventory_summaries(session: AsyncSession) -> pd.DataFrame:
    """ดึงข้อมูล inventory ทั้งหมดจาก monthly_inventories (หรือ fallback daily/summaries)."""
    stmt = text("""
        SELECT time as recorded_at, total_boxes as quantity
        FROM monthly_inventories
        ORDER BY time ASC
    """)
    result = await session.execute(stmt)
    rows = result.fetchall()
    if rows:
        df = pd.DataFrame(rows, columns=["recorded_at", "quantity"])
        df["recorded_at"] = pd.to_datetime(df["recorded_at"], utc=True)
        df["quantity"] = df["quantity"].astype(float)
        return df

    # Fallback to daily_inventories
    stmt_d = text("""
        SELECT time as recorded_at, total_boxes as quantity
        FROM daily_inventories
        ORDER BY time ASC
    """)
    res_d = await session.execute(stmt_d)
    rows_d = res_d.fetchall()
    if rows_d:
        df = pd.DataFrame(rows_d, columns=["recorded_at", "quantity"])
        df["recorded_at"] = pd.to_datetime(df["recorded_at"], utc=True)
        df["quantity"] = df["quantity"].astype(float)
        return df

    # Fallback to legacy inventory_summaries
    stmt_old = text("""
        SELECT date as recorded_at, total_boxes as quantity
        FROM inventory_summaries
        ORDER BY date ASC
    """)
    res_old = await session.execute(stmt_old)
    rows_old = res_old.fetchall()
    if rows_old:
        df = pd.DataFrame(rows_old, columns=["recorded_at", "quantity"])
        df["recorded_at"] = pd.to_datetime(df["recorded_at"], utc=True)
        df["quantity"] = df["quantity"].astype(float)
        return df

    return pd.DataFrame(columns=["recorded_at", "quantity"])


async def _fetch_camera_exog(session: AsyncSession) -> pd.DataFrame:
    """ดึง detected_count รายเดือนจาก box_logs หรือ camera_logs เพื่อใช้เป็น exogenous variable."""
    stmt = text("""
        SELECT date_trunc('month', time AT TIME ZONE 'UTC') AS month,
               AVG(total_boxes) AS detected_stock
        FROM box_logs
        GROUP BY 1
        ORDER BY 1 ASC
    """)
    result = await session.execute(stmt)
    rows = result.fetchall()
    if rows:
        df = pd.DataFrame(rows, columns=["recorded_at", "detected_stock"])
        df["recorded_at"] = pd.to_datetime(df["recorded_at"], utc=True)
        return df

    # Fallback to legacy camera_logs
    stmt_old = text("""
        SELECT date_trunc('month', captured_at AT TIME ZONE 'UTC') AS month,
               AVG(detected_count) AS detected_stock
        FROM camera_logs
        WHERE processing_status = 'processed'
        GROUP BY 1
        ORDER BY 1 ASC
    """)
    res_old = await session.execute(stmt_old)
    rows_old = res_old.fetchall()
    if rows_old:
        df = pd.DataFrame(rows_old, columns=["recorded_at", "detected_stock"])
        df["recorded_at"] = pd.to_datetime(df["recorded_at"], utc=True)
        return df

    return pd.DataFrame(columns=["recorded_at", "detected_stock"])


# ---------------------------------------------------------------------------
# Core Training Logic
# ---------------------------------------------------------------------------

def _load_csv_fallback(product: str) -> pd.DataFrame:
    """อ่าน inventory CSV ตาม path เดียวกับขั้นตอน import และ prediction."""
    csv_path = get_inventory_csv_path()
    logger.info("Reading inventory CSV fallback from %s for product '%s'", csv_path, product)
    return load_inventory_time_series(csv_path)


async def train_arima_model(
    job_id: str,
    product: str,
    p: Optional[int] = 1,
    d: Optional[int] = 1,
    q: Optional[int] = 1,
    forecast_horizon: int = 3,
    warehouse: Optional[str] = None,
    auto_order: bool = True,
) -> dict:
    """
    Pipeline หลักสำหรับเทรน ARIMA:

    1. ดึงข้อมูลจาก PostgreSQL (stock + camera exog)
    2. Fallback ไปใช้ CSV ถ้า DB มีข้อมูล < MIN_MONTHS_REQUIRED
    3. Preprocess → Monthly resample
    4. Auto ACF/PACF & AIC order selection (ถ้า auto_order=True หรือใช้ค่าเริ่มต้น)
    5. Chronological split → Evaluate metrics (ถ้าข้อมูลพอ)
    6. Train full model
    7. Serialize → Upload ขึ้น MinIO
    8. คืนสรุปผล
    """
    MIN_MONTHS_REQUIRED = 12  # ARIMA ต้องการข้อมูลอย่างน้อย 12 เดือนสำหรับ split ที่ดี
    if warehouse:
        raise ValueError(
            "Inventory summary data has no warehouse column; warehouse filtering is unsupported"
        )

    # ใช้ path เดิมที่มีอยู่แล้วในระบบ inference_worker
    import sys
    workspace_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    backend_src = os.path.join(os.path.dirname(workspace_root), "backend", "src")
    inference_src = os.path.join(workspace_root, "inference_worker")
    for p_ in [backend_src, inference_src, workspace_root]:
        if p_ not in sys.path:
            sys.path.insert(0, p_)

    from forecast_model.preprocessing import prepare_time_series, chronological_split, PreprocessingError
    from forecast_model.arima import train_arima, forecast_arima, select_optimal_arima_order
    from forecast_model.metrics import calculate_mae, calculate_rmse, calculate_mape

    database_url = os.getenv("DATABASE_URL", "postgresql://admin:secretpassword@postgres:5432/my_database")
    session_factory, engine = _make_session_factory(database_url)

    # 1. Fetch data from PostgreSQL
    try:
        async with session_factory() as session:
            stock_df = await _fetch_inventory_summaries(session)
            camera_df = await _fetch_camera_exog(session)
    finally:
        await engine.dispose()

    logger.info("DB returned %d stock rows for '%s'", len(stock_df), product)

    # 2. Aggregate เป็นรายเดือนก่อนตรวจจำนวน
    use_csv_fallback = False
    if not stock_df.empty:
        temp_df = stock_df.copy()
        temp_df["recorded_at"] = pd.to_datetime(temp_df["recorded_at"], utc=True)
        temp_df = temp_df.set_index("recorded_at")
        monthly_count = temp_df.resample("MS")["quantity"].sum()
        n_months = len(monthly_count.dropna())
    else:
        n_months = 0

    if n_months < MIN_MONTHS_REQUIRED:
        logger.warning(
            "DB has only %d months (need %d) for '%s' — falling back to CSV",
            n_months, MIN_MONTHS_REQUIRED, product
        )
        use_csv_fallback = True
        stock_df = _load_csv_fallback(product)
        if stock_df.empty:
            raise ValueError(
                f"ไม่พบข้อมูลสต็อก '{product}' ทั้งใน PostgreSQL ({n_months} เดือน) "
                f"และ CSV fallback"
            )
        logger.info("CSV fallback loaded %d rows", len(stock_df))

    # 3. Merge camera exog (ถ้ามีและไม่ได้ใช้ CSV fallback)
    if not camera_df.empty and not use_csv_fallback:
        df = pd.merge(stock_df, camera_df, on="recorded_at", how="outer")
        df["quantity"] = df["quantity"].fillna(0.0)
        df["detected_stock"] = df["detected_stock"].fillna(0.0)
        exog_cols = ["detected_stock"]
        logger.info("Using camera_logs as exogenous variable (%d rows)", len(camera_df))
    else:
        df = stock_df
        exog_cols = []
        if use_csv_fallback:
            logger.info("Using CSV fallback data (no exog)")
        else:
            logger.info("No camera_logs available; training ARIMA without exogenous variable")

    # 4. Preprocess → monthly resample
    monthly_df = prepare_time_series(df, target_col="quantity", date_col="recorded_at")
    logger.info("Monthly data shape: %s, date range: %s → %s",
                monthly_df.shape, monthly_df.index[0], monthly_df.index[-1])

    # 4.1 Auto ACF/PACF & AIC order selection
    # ถ้าเปิด auto_order หรือพารามิเตอร์เป็นค่าเริ่มต้น (1, 1, 1) หรือไม่ได้ระบุ จะวิเคราะห์สถิติเพื่อหา Order ที่เหมาะสมที่สุด
    used_auto_order = False
    if auto_order or (p is None or d is None or q is None) or (p == 1 and d == 1 and q == 1):
        try:
            logger.info("Analyzing ADF, ACF, and PACF to find optimal (p, d, q)...")
            opt_p, opt_d, opt_q = select_optimal_arima_order(
                monthly_df, target_col="quantity", exog_cols=exog_cols
            )
            logger.info("Auto ACF/PACF selection result: ARIMA(%d,%d,%d) (was (%s,%s,%s))",
                        opt_p, opt_d, opt_q, p, d, q)
            p, d, q = opt_p, opt_d, opt_q
            used_auto_order = True
        except Exception as e:
            logger.warning("Auto ARIMA order selection failed (%s); using (%s,%s,%s)", e, p, d, q)
            p = p or 1
            d = d or 1
            q = q or 1
    else:
        logger.info("Using specified ARIMA order: (%d,%d,%d)", p, d, q)

    # 5. Evaluate metrics (chronological 80/20 split) — only if enough data
    mae, rmse, mape_val = 0.0, 0.0, 0.0
    if len(monthly_df) >= 10:
        try:
            train_df, test_df = chronological_split(monthly_df, train_ratio=0.8)
            eval_model = train_arima(train_df, "quantity", exog_cols, p, d, q)
            future_exog = test_df[exog_cols] if exog_cols else None
            test_forecast, _ = forecast_arima(eval_model, steps=len(test_df), future_exog=future_exog)
            y_true = test_df["quantity"].values
            y_pred = test_forecast.values
            mae = calculate_mae(y_true, y_pred)
            rmse = calculate_rmse(y_true, y_pred)
            mape_val = calculate_mape(y_true, y_pred)
            logger.info("Eval metrics — MAE=%.4f RMSE=%.4f MAPE=%.2f%%", mae, rmse, mape_val)
        except PreprocessingError as e:
            logger.warning("Skipping metric evaluation: %s", e)
        except Exception as e:
            logger.warning("Metric evaluation failed (non-critical): %s", e)
    else:
        logger.warning(
            "Only %d months available — skipping metric evaluation (need >= 10)",
            len(monthly_df)
        )

    # 6. Train full model
    logger.info("Training full ARIMA(%d,%d,%d) on %d months...", p, d, q, len(monthly_df))
    full_model = train_arima(monthly_df, "quantity", exog_cols, p, d, q)
    logger.info("Training complete")

    # 7. Serialize → pickle bytes
    buf = io.BytesIO()
    full_model.save(buf)
    model_bytes = buf.getvalue()

    # 8. Upload ขึ้น MinIO
    minio_client = _get_minio_client()
    model_bucket = "models"
    model_key = f"arima/{product}/{job_id}/model.pkl"
    local_model_path = get_local_arima_model_path(product)
    local_model_path.parent.mkdir(parents=True, exist_ok=True)
    local_model_path.write_bytes(model_bytes)
    logger.info("Saved trained ARIMA model to shared storage: %s", local_model_path)
    _upload_bytes(minio_client, model_bucket, model_key, model_bytes, "application/octet-stream")

    # ยังอัปโหลด metrics JSON ด้วย
    import json
    metrics = {
        "mae": mae, "rmse": rmse, "mape": mape_val,
        "p": p, "d": d, "q": q,
        "model_order": f"ARIMA({p},{d},{q})",
        "auto_order_used": used_auto_order,
        "forecast_horizon": forecast_horizon,
        "n_train_months": len(monthly_df),
        "product": product,
        "data_source": "csv_fallback" if use_csv_fallback else "postgresql",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "local_model_path": str(local_model_path),
    }
    metrics_bytes = json.dumps(metrics, indent=2).encode()
    local_metrics_path = local_model_path.with_suffix(".json")
    local_metrics_path.write_bytes(metrics_bytes)
    metrics_key = f"arima/{product}/{job_id}/metrics.json"
    _upload_bytes(minio_client, model_bucket, metrics_key, metrics_bytes, "application/json")

    minio_uri = f"minio://{model_bucket}/{model_key}"
    logger.info("ARIMA training job %s done. Model at %s", job_id, minio_uri)

    return {
        "status": "success",
        "model_type": "arima",
        "product": product,
        "job_id": job_id,
        "model_uri": minio_uri,
        "metrics": metrics,
    }
