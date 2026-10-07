"""ARIMA Trainer: ดึงข้อมูลจาก PostgreSQL → เทรน → MLflow Tracking → อัปโหลดโมเดล + metrics ขึ้น MinIO

Flow:
    1. ดึง inventory จาก monthly_inventories / daily_inventories ใน PostgreSQL (หรือ fallback CSV)
    2. ดึง camera_logs / box_logs (detected_count) เพื่อใช้เป็น exogenous variable
    3. Chronological 80/20 train/test split (ไม่มีการสุ่มสลับ ป้องกัน data leakage)
    4. ประเมินผลเปรียบเทียบกับ Naïve และ Seasonal-Naïve Baselines (MAE, RMSE, MAPE)
    5. ป้องกันค่าที่คำนวณไม่ได้ไม่ให้แสดงเป็น 0.0 โดยใช้ None/null อย่างชัดเจน
    6. เทรนโมเดลเต็มชุด → serialize เป็น .pkl
    7. บันทึก Parameters, Metrics, Tags, และ Artifacts ลงใน MLflow (MinIO s3://mlflow-artifacts)
    8. อัปโหลดไฟล์โมเดลขึ้น MinIO bucket "models" ที่ key arima/<product>/<job_id>/model.pkl
    9. คืน dict สรุปผลพร้อม MinIO URI และ MLflow Run ID
"""
from __future__ import annotations

import io
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

import numpy as np
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


async def _fetch_inventory_summaries(session: AsyncSession, product: Optional[str] = None) -> pd.DataFrame:
    """ดึงข้อมูล inventory จาก monthly_inventories โดยกรองตาม product ถ้ามี หรือ fallback daily_inventories."""
    clean_prod = product.replace("_", " ").strip() if product else ""
    
    # 1. พยายามค้นหาตามชื่อสินค้าใน monthly_inventories
    if clean_prod:
        stmt_prod = text("""
            SELECT time as recorded_at, total_boxes as quantity
            FROM monthly_inventories
            WHERE LOWER(product) = LOWER(:p) OR LOWER(product) LIKE LOWER(:p_like)
            ORDER BY time ASC
        """)
        res_prod = await session.execute(stmt_prod, {"p": clean_prod, "p_like": f"%{clean_prod}%"})
        rows_prod = res_prod.fetchall()
        if rows_prod:
            df = pd.DataFrame(rows_prod, columns=["recorded_at", "quantity"])
            df["recorded_at"] = pd.to_datetime(df["recorded_at"], utc=True)
            df["quantity"] = df["quantity"].astype(float)
            logger.info("Found %d monthly_inventories matching product '%s'", len(df), clean_prod)
            return df

    # 2. ถ้าไม่พบหรือไม่ได้ระบุ ให้ดึงข้อมูลทั้งหมดใน monthly_inventories (เช่น Frozen Shrimp 70 แถว)
    stmt_all = text("""
        SELECT time as recorded_at, total_boxes as quantity
        FROM monthly_inventories
        ORDER BY time ASC
    """)
    result = await session.execute(stmt_all)
    rows = result.fetchall()
    if rows:
        df = pd.DataFrame(rows, columns=["recorded_at", "quantity"])
        df["recorded_at"] = pd.to_datetime(df["recorded_at"], utc=True)
        df["quantity"] = df["quantity"].astype(float)
        logger.info("Fetched all %d rows from monthly_inventories", len(df))
        return df

    # 3. Fallback ไปยัง daily_inventories
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
        logger.info("Fetched %d rows from daily_inventories", len(df))
        return df

    return pd.DataFrame(columns=["recorded_at", "quantity"])


async def _fetch_camera_exog(session: AsyncSession) -> pd.DataFrame:
    """ดึง detected_count รายเดือนจาก box_logs เพื่อใช้เป็น exogenous variable."""
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

    return pd.DataFrame(columns=["recorded_at", "detected_stock"])


def _load_csv_fallback(product: str) -> pd.DataFrame:
    """อ่าน inventory CSV fallback."""
    csv_path = get_inventory_csv_path()
    logger.info("Reading inventory CSV fallback from %s for product '%s'", csv_path, product)
    return load_inventory_time_series(csv_path)


# ---------------------------------------------------------------------------
# Core Training Logic with MLflow Tracking & Baselines
# ---------------------------------------------------------------------------

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

    1. ดึงข้อมูลจาก PostgreSQL (monthly_inventories / daily_inventories + camera exog)
    2. Fallback ไปใช้ CSV ถ้า DB มีข้อมูล < MIN_MONTHS_REQUIRED
    3. Preprocess → Monthly resample
    4. Auto ACF/PACF & AIC order selection (ถ้า auto_order=True)
    5. Chronological holdout evaluation (80/20) → เปรียบเทียบกับ Naïve & Seasonal Naïve baselines
    6. ป้องกันกรณี metric คำนวณไม่ได้ถูกส่งเป็น 0.0 โดยระบุเป็น None ชัดเจน
    7. Train full model → คำนวณ AIC, BIC
    8. บันทึกพารามิเตอร์, ตัวชี้วัด, Tags, และ Artifacts เข้าสู่ MLflow (MinIO s3://mlflow-artifacts)
    9. Serialize → Upload ขึ้น MinIO bucket "models"
    10. คืนสรุปผลพร้อม model_uri และ mlflow_run_id
    """
    MIN_MONTHS_REQUIRED = 12
    if warehouse:
        raise ValueError("Inventory summary data has no warehouse column; warehouse filtering is unsupported")

    # ตั้งค่า Environment สำหรับ MLflow และ MinIO S3
    mlflow_tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
    minio_endpoint = os.getenv("MINIO_ENDPOINT", "minio:9000")
    os.environ["MLFLOW_TRACKING_URI"] = mlflow_tracking_uri
    os.environ["AWS_ACCESS_KEY_ID"] = os.getenv("MINIO_ACCESS_KEY", "admin")
    os.environ["AWS_SECRET_ACCESS_KEY"] = os.getenv("MINIO_SECRET_KEY", "password123")
    os.environ["MLFLOW_S3_ENDPOINT_URL"] = os.getenv("MLFLOW_S3_ENDPOINT_URL", f"http://{minio_endpoint}")
    os.environ["GIT_PYTHON_REFRESH"] = "quiet"

    import sys
    workspace_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    backend_src = os.path.join(os.path.dirname(workspace_root), "backend", "src")
    inference_src = os.path.join(workspace_root, "inference_worker")
    for p_ in [backend_src, inference_src, workspace_root]:
        if p_ not in sys.path:
            sys.path.insert(0, p_)

    from forecast_model.preprocessing import prepare_time_series, chronological_split, PreprocessingError
    from forecast_model.arima import train_arima, forecast_arima, select_optimal_arima_order
    from forecast_model.metrics import (
        calculate_mae, calculate_rmse, calculate_mape,
        evaluate_forecast_against_baselines
    )

    database_url = os.getenv("DATABASE_URL", "postgresql://admin:secretpassword@postgres:5432/my_database")
    session_factory, engine = _make_session_factory(database_url)

    # 1. Fetch data from PostgreSQL
    try:
        async with session_factory() as session:
            stock_df = await _fetch_inventory_summaries(session, product=product)
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

    # 3. Merge camera exog
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

    # 5. Chronological holdout evaluation (80/20 split) & Baseline Comparison
    eval_done = False
    eval_res: Dict[str, Any] = {}
    mae: Optional[float] = None
    rmse: Optional[float] = None
    mape_val: Optional[float] = None
    train_df = None
    test_df = None
    y_train = None
    y_true = None
    y_pred = None

    if len(monthly_df) >= 10:
        try:
            # Chronological split ป้องกัน data leakage โดยเด็ดขาด
            train_df, test_df = chronological_split(monthly_df, train_ratio=0.8)
            eval_model = train_arima(train_df, "quantity", exog_cols, p, d, q)
            future_exog = test_df[exog_cols] if exog_cols else None
            test_forecast, _ = forecast_arima(eval_model, steps=len(test_df), future_exog=future_exog)
            
            y_train = train_df["quantity"].values
            y_true = test_df["quantity"].values
            y_pred = test_forecast.values

            eval_res = evaluate_forecast_against_baselines(
                y_train=y_train,
                y_true=y_true,
                y_pred=y_pred,
                season_length=12
            )
            mae = eval_res["mae"]
            rmse = eval_res["rmse"]
            mape_val = eval_res["mape"]
            eval_done = True

            logger.info("Chronological Eval (Holdout) — MAE=%.4f RMSE=%.4f MAPE=%s",
                        mae, rmse, f"{mape_val:.2f}%" if mape_val is not None else "None (zero actuals)")
            logger.info("Baseline comparison — Naive MAE=%.4f | Seasonal-Naive MAE=%.4f",
                        eval_res["baselines"]["naive"]["mae"],
                        eval_res["baselines"]["seasonal_naive"]["mae"])
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

    aic_val: Optional[float] = None
    bic_val: Optional[float] = None
    try:
        aic_val = float(full_model.aic)
        bic_val = float(full_model.bic)
        logger.info("Full model stats: AIC=%.2f BIC=%.2f", aic_val, bic_val)
    except Exception:
        pass

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

    # Metrics dictionary พร้อม baselines
    metrics: Dict[str, Any] = {
        "mae": mae,
        "rmse": rmse,
        "mape": mape_val,
        "aic": aic_val,
        "bic": bic_val,
        "p": p,
        "d": d,
        "q": q,
        "model_order": f"ARIMA({p},{d},{q})",
        "auto_order_used": used_auto_order,
        "forecast_horizon": forecast_horizon,
        "n_train_months": len(monthly_df),
        "product": product,
        "data_source": "csv_fallback" if use_csv_fallback else "postgresql",
        "eval_method": "chronological_holdout_80_20" if eval_done else "none",
        "baselines": eval_res.get("baselines"),
        "evaluation_notes": eval_res.get("evaluation_notes"),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "local_model_path": str(local_model_path),
    }

    metrics_bytes = json.dumps(metrics, indent=2, ensure_ascii=False).encode()
    local_metrics_path = local_model_path.with_suffix(".json")
    local_metrics_path.write_bytes(metrics_bytes)
    metrics_key = f"arima/{product}/{job_id}/metrics.json"
    _upload_bytes(minio_client, model_bucket, metrics_key, metrics_bytes, "application/json")

    minio_uri = f"minio://{model_bucket}/{model_key}"

    # 9. MLflow Tracking: Log Parameters, Metrics, Tags, and Artifacts
    mlflow_run_id = None
    mlflow_experiment = os.getenv("MLFLOW_EXPERIMENT_NAME", "arima-inventory-forecasting")
    try:
        import mlflow
        mlflow.set_tracking_uri(mlflow_tracking_uri)
        mlflow.set_experiment(mlflow_experiment)

        run_name = f"arima-{product}-{job_id[:8]}"
        with mlflow.start_run(run_name=run_name) as run:
            mlflow_run_id = run.info.run_id

            # Parameters
            mlflow.log_params({
                "product": product,
                "p": p,
                "d": d,
                "q": q,
                "model_order": f"ARIMA({p},{d},{q})",
                "auto_order_used": str(used_auto_order),
                "forecast_horizon": forecast_horizon,
                "n_train_months": len(monthly_df),
                "data_source": "csv_fallback" if use_csv_fallback else "postgresql",
                "eval_method": "chronological_holdout_80_20",
                "season_length": 12,
            })

            # Tags
            mlflow.set_tags({
                "job_id": job_id,
                "product": product,
                "model_type": "arima",
                "framework": "statsmodels",
                "data_source": "csv_fallback" if use_csv_fallback else "postgresql",
                "eval_status": "evaluated" if eval_done else "not_evaluatable",
                "minio_model_uri": minio_uri,
            })

            # Metrics
            mlflow_metrics = {}
            if aic_val is not None:
                mlflow_metrics["aic"] = aic_val
            if bic_val is not None:
                mlflow_metrics["bic"] = bic_val
            if mae is not None:
                mlflow_metrics["mae"] = mae
            if rmse is not None:
                mlflow_metrics["rmse"] = rmse
            if mape_val is not None:
                mlflow_metrics["mape"] = mape_val

            if eval_done and "baselines" in eval_res:
                b_naive = eval_res["baselines"]["naive"]
                b_snaive = eval_res["baselines"]["seasonal_naive"]
                if b_naive.get("mae") is not None:
                    mlflow_metrics["naive_mae"] = float(b_naive["mae"])
                if b_naive.get("rmse") is not None:
                    mlflow_metrics["naive_rmse"] = float(b_naive["rmse"])
                if b_naive.get("mape") is not None:
                    mlflow_metrics["naive_mape"] = float(b_naive["mape"])
                if b_snaive.get("mae") is not None:
                    mlflow_metrics["snaive_mae"] = float(b_snaive["mae"])
                if b_snaive.get("rmse") is not None:
                    mlflow_metrics["snaive_rmse"] = float(b_snaive["rmse"])
                if b_snaive.get("mape") is not None:
                    mlflow_metrics["snaive_mape"] = float(b_snaive["mape"])

            if mlflow_metrics:
                mlflow.log_metrics(mlflow_metrics)

            # Artifacts (upload to MinIO via MLflow artifact store)
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_model = os.path.join(tmp_dir, "model.pkl")
                with open(tmp_model, "wb") as f_m:
                    f_m.write(model_bytes)

                tmp_metrics = os.path.join(tmp_dir, "metrics.json")
                with open(tmp_metrics, "wb") as f_mt:
                    f_mt.write(metrics_bytes)

                # สร้างกราฟเปรียบเทียบผลพยากรณ์กับค่าจริงและ baseline
                if eval_done and train_df is not None and test_df is not None:
                    try:
                        import matplotlib
                        matplotlib.use("Agg")
                        import matplotlib.pyplot as plt

                        fig, ax = plt.subplots(figsize=(10, 5), dpi=100)
                        test_dates = test_df.index
                        ax.plot(train_df.index, y_train, label="Train History", color="#2563eb", linewidth=1.5)
                        ax.plot(test_dates, y_true, label="Test Ground Truth", color="#16a34a", marker="o", linewidth=2)
                        ax.plot(test_dates, y_pred, label=f"ARIMA({p},{d},{q}) Pred", color="#dc2626", linestyle="--", marker="s", linewidth=2)
                        
                        naive_line = np.full(len(test_dates), y_train[-1])
                        ax.plot(test_dates, naive_line, label="Naïve Baseline", color="#64748b", linestyle=":", linewidth=1.5)

                        ax.set_title(f"ARIMA Demand Forecast vs Ground Truth & Baselines ({product})", fontsize=12, fontweight="bold")
                        ax.set_xlabel("Date", fontsize=10)
                        ax.set_ylabel("Quantity (Boxes)", fontsize=10)
                        ax.legend(loc="upper left")
                        ax.grid(True, linestyle="--", alpha=0.5)
                        fig.tight_layout()

                        plot_file = os.path.join(tmp_dir, "forecast_evaluation.png")
                        fig.savefig(plot_file)
                        plt.close(fig)
                    except Exception as e_plot:
                        logger.warning("Could not generate evaluation plot: %s", e_plot)

                mlflow.log_artifacts(tmp_dir, artifact_path="arima_model")

            logger.info("MLflow tracking completed: run_id=%s [Experiment: %s]", mlflow_run_id, mlflow_experiment)

    except Exception as e_mlflow:
        logger.warning("MLflow tracking encountered warning: %s", e_mlflow, exc_info=True)

    metrics["mlflow_run_id"] = mlflow_run_id
    metrics["mlflow_experiment"] = mlflow_experiment
    logger.info("ARIMA training job %s done. Model at %s (MLflow Run: %s)", job_id, minio_uri, mlflow_run_id)

    return {
        "status": "success",
        "model_type": "arima",
        "product": product,
        "job_id": job_id,
        "model_uri": minio_uri,
        "mlflow_run_id": mlflow_run_id,
        "mlflow_experiment": mlflow_experiment,
        "metrics": metrics,
    }
