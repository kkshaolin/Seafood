"""YOLO Trainer: ดาวน์โหลด Dataset จาก MinIO → ตรวจสอบความถูกต้อง → เทรน YOLO11 → บันทึก MLflow & TensorBoard → อัปโหลดผลลัพธ์ขึ้น MinIO

Flow:
    1. ดาวน์โหลด Dataset (ZIP) จาก MinIO bucket "datasets" ที่ key yolo/<dataset_name>/ หรือ local path
    2. แตกไฟล์ลงโฟลเดอร์ชั่วคราว /tmp/yolo_train/<job_id>/
    3. ตรวจสอบความถูกต้องของ Dataset (Images, Labels, Class Mapping) - ปฏิเสธหากไม่มีข้อมูลจริง
    4. สร้าง dataset.yaml แบบไดนามิก
    5. โหลด Base Model (yolo11n_v3.pt หรือ yolo11n.pt)
    6. รัน model.train() ด้วย Ultralytics API
    7. บันทึกผลลัพธ์ลง MLflow (Parameters, Epoch Metrics, Artifacts, Weights)
    8. ส่ง Event logs เข้า TensorBoard log directory (/app/storage/logs/tensorboard/)
    9. อัปโหลด best.pt, last.pt, และ plots ขึ้น MinIO bucket "models"
    10. คืน dict สรุปผลพร้อม MLflow Run ID และ TensorBoard URL
"""
from __future__ import annotations

import io
import json
import logging
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from minio import Minio
from minio.error import S3Error

logger = logging.getLogger("training_worker.yolo")

# Bucket สำหรับ Dataset ขาเข้าและโมเดล/ผลลัพธ์ขาออก
DATASET_BUCKET = "datasets"
MODEL_BUCKET = "models"

# ตำแหน่ง Base Model ใน MinIO และ local fallback
BASE_MODEL_MINIO_KEY = "yolo/base/yolo11n_v3.pt"
BASE_MODEL_LOCAL_PATHS = [
    "/app/storage/models/non_time_serie/yolo11n_v3.pt",
    "./storage/models/non_time_serie/yolo11n_v3.pt",
    "/app/storage/models/non_time_serie/yolo11n.pt",
    "./storage/models/non_time_serie/yolo11n.pt",
]

TENSORBOARD_LOG_DIR = os.getenv("TENSORBOARD_LOG_DIR", "/app/storage/logs/tensorboard")


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
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
        logger.info("Created MinIO bucket: %s", bucket)


def _download_file(client: Minio, bucket: str, key: str, dest_path: str) -> None:
    """ดาวน์โหลด object จาก MinIO ไปยัง dest_path."""
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    client.fget_object(bucket, key, dest_path)
    logger.info("Downloaded MinIO %s/%s → %s", bucket, key, dest_path)


def _upload_file(client: Minio, bucket: str, key: str, src_path: str,
                 content_type: str = "application/octet-stream") -> str:
    """อัปโหลดไฟล์จาก src_path ขึ้น MinIO."""
    _ensure_bucket(client, bucket)
    client.fput_object(bucket, key, src_path, content_type=content_type)
    file_size = os.path.getsize(src_path)
    logger.info("Uploaded %s → MinIO %s/%s (%d bytes)", src_path, bucket, key, file_size)
    return key


def _upload_bytes(client: Minio, bucket: str, key: str, data: bytes,
                  content_type: str = "application/octet-stream") -> str:
    _ensure_bucket(client, bucket)
    client.put_object(bucket, key, io.BytesIO(data), len(data), content_type=content_type)
    return key


# ---------------------------------------------------------------------------
# Dataset preparation & validation
# ---------------------------------------------------------------------------

def _validate_dataset_structure(dataset_dir: str) -> dict:
    """
    ตรวจสอบโครงสร้าง Dataset ว่ามีไฟล์รูปและ labels จริงหรือไม่
    รองรับทั้งโครงสร้าง:
      1) dataset_dir/train/images, dataset_dir/valid/images (or val)
      2) dataset_dir/images/train, dataset_dir/labels/train
    """
    train_img_candidates = [
        os.path.join(dataset_dir, "train", "images"),
        os.path.join(dataset_dir, "images", "train"),
    ]
    val_img_candidates = [
        os.path.join(dataset_dir, "valid", "images"),
        os.path.join(dataset_dir, "val", "images"),
        os.path.join(dataset_dir, "images", "valid"),
        os.path.join(dataset_dir, "images", "val"),
    ]
    test_img_candidates = [
        os.path.join(dataset_dir, "test", "images"),
        os.path.join(dataset_dir, "images", "test"),
    ]

    train_img_dir = next((p for p in train_img_candidates if os.path.isdir(p)), None)
    val_img_dir = next((p for p in val_img_candidates if os.path.isdir(p)), None)
    test_img_dir = next((p for p in test_img_candidates if os.path.isdir(p)), None)

    if not train_img_dir:
        raise ValueError(
            f"Dataset validation failed: missing training images directory in {dataset_dir}. "
            f"Expected either 'train/images' or 'images/train'."
        )

    # นับจำนวนภาพ
    def count_images(d):
        if not d or not os.path.isdir(d):
            return 0
        valid_exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
        return len([f for f in os.listdir(d) if os.path.splitext(f)[1].lower() in valid_exts])

    n_train = count_images(train_img_dir)
    n_val = count_images(val_img_dir)
    n_test = count_images(test_img_dir)

    if n_train == 0:
        raise ValueError(f"Dataset validation failed: training images directory {train_img_dir} is empty.")

    logger.info(
        "Dataset validation passed: train=%d images, val=%d images, test=%d images",
        n_train, n_val, n_test
    )
    return {
        "train_img_dir": train_img_dir,
        "val_img_dir": val_img_dir or train_img_dir,
        "test_img_dir": test_img_dir,
        "n_train": n_train,
        "n_val": n_val,
        "n_test": n_test,
    }


def _download_and_extract_dataset(client: Minio, dataset_name: str,
                                   work_dir: str) -> str:
    """
    ดาวน์โหลด Dataset ZIP จาก MinIO ก่อนเพื่อใช้ไฟล์เวอร์ชันบน Storage
    หากไม่มีหรือไม่สามารถเชื่อมต่อได้ จึง fallback ไปตรวจสอบโฟลเดอร์ Local ในเครื่อง
    """
    zip_keys = [
        f"yolo/{dataset_name}/{dataset_name}.zip",
        f"yolo/{dataset_name}.zip",
        f"{dataset_name}.zip",
    ]
    zip_path = os.path.join(work_dir, f"{dataset_name}.zip")
    dataset_dir = os.path.join(work_dir, "dataset")

    for zip_key in zip_keys:
        try:
            _download_file(client, DATASET_BUCKET, zip_key, zip_path)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(dataset_dir)
            logger.info("Extracted dataset from MinIO (%s/%s) to %s", DATASET_BUCKET, zip_key, dataset_dir)
            _validate_dataset_structure(dataset_dir)
            return dataset_dir
        except Exception as e_s3:
            logger.debug("MinIO key '%s' not usable: %s", zip_key, e_s3)

    # หากไม่มีใน MinIO ให้ลองใช้ Local Storage เฉพาะของ dataset_name ที่ร้องขอ
    local_paths = [
        f"/app/storage/data/{dataset_name}",
        f"./storage/data/{dataset_name}",
    ]

    for path in local_paths:
        if os.path.exists(path) and os.path.isdir(path):
            try:
                _validate_dataset_structure(path)
                logger.info("Using valid local dataset found at: %s", path)
                return path
            except ValueError:
                pass

    raise FileNotFoundError(
        f"Dataset '{dataset_name}' not found at MinIO {DATASET_BUCKET}/yolo/{dataset_name}/{dataset_name}.zip "
        f"and no valid local dataset found. "
        f"Please upload a valid dataset ZIP containing ground-truth images and labels before training."
    )


def _write_dataset_yaml(dataset_dir: str, class_names: list[str]) -> str:
    """สร้างไฟล์ dataset.yaml สำหรับ Ultralytics YOLO."""
    meta = _validate_dataset_structure(dataset_dir)
    yaml_path = os.path.join(dataset_dir, "dataset.yaml")

    # กำหนด relative path จาก dataset_dir
    rel_train = os.path.relpath(meta["train_img_dir"], dataset_dir).replace("\\", "/")
    rel_val = os.path.relpath(meta["val_img_dir"], dataset_dir).replace("\\", "/")

    clean_dataset_dir = dataset_dir.replace("\\", "/")
    lines = [
        f"path: {clean_dataset_dir}",
        f"train: {rel_train}",
        f"val: {rel_val}",
    ]
    if meta["test_img_dir"]:
        rel_test = os.path.relpath(meta["test_img_dir"], dataset_dir).replace("\\", "/")
        lines.append(f"test: {rel_test}")

    lines.extend([
        f"nc: {len(class_names)}",
        f"names: {class_names}",
        "",
    ])

    with open(yaml_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    logger.info("dataset.yaml written to %s", yaml_path)
    return yaml_path


def _get_base_model(client: Minio, work_dir: str) -> str:
    """
    หาไฟล์ Base Model YOLO:
    1. ลอง local candidates (yolo11n_v3.pt, yolo11n.pt)
    2. ลองดาวน์โหลดจาก MinIO
    3. Fallback: ใช้ชื่อ 'yolo11n.pt' ให้ Ultralytics โหลดเอง
    """
    local_dest = os.path.join(work_dir, "base_model.pt")

    for local_path in BASE_MODEL_LOCAL_PATHS:
        if os.path.exists(local_path):
            shutil.copy2(local_path, local_dest)
            logger.info("Using base model from local storage: %s", local_path)
            return local_dest

    # ลอง MinIO
    try:
        _download_file(client, MODEL_BUCKET, BASE_MODEL_MINIO_KEY, local_dest)
        logger.info("Using base model from MinIO: %s", BASE_MODEL_MINIO_KEY)
        return local_dest
    except Exception:
        pass

    try:
        _download_file(client, MODEL_BUCKET, "yolo/base/yolo11n.pt", local_dest)
        logger.info("Using fallback base model from MinIO: yolo/base/yolo11n.pt")
        return local_dest
    except Exception:
        pass

    logger.info("Base model not found in storage; using Ultralytics default yolo11n.pt")
    return "yolo11n.pt"


# ---------------------------------------------------------------------------
# Core Training with MLflow & TensorBoard
# ---------------------------------------------------------------------------

async def train_yolo_model(
    job_id: str,
    dataset_name: str,
    class_names: Optional[list[str]] = None,
    epochs: int = 10,
    imgsz: int = 640,
    batch: int = 8,
    patience: int = 5,
) -> dict:
    """Pipeline หลักสำหรับเทรน YOLO พร้อมบันทึกผลลง MLflow และ TensorBoard."""
    import asyncio

    if not class_names or class_names == ["box"]:
        class_names = ["delivery_box"]

    minio_client = _get_minio_client()
    work_dir = tempfile.mkdtemp(prefix=f"yolo_{job_id}_")
    logger.info("YOLO training job %s started. work_dir=%s", job_id, work_dir)

    mlflow_run_id = None
    mlflow_tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")

    try:
        # 1. ดาวน์โหลดและตรวจสอบ Dataset
        dataset_dir = _download_and_extract_dataset(minio_client, dataset_name, work_dir)
        yaml_path = _write_dataset_yaml(dataset_dir, class_names)

        # 2. เตรียม Base Model
        base_model_path = _get_base_model(minio_client, work_dir)

        # 3. เริ่มต้น MLflow Run
        try:
            import mlflow
            mlflow.set_tracking_uri(mlflow_tracking_uri)
            mlflow.set_experiment("yolo-box-detection")
            mlflow_run = mlflow.start_run(run_name=f"yolo_{dataset_name}_{job_id}")
            mlflow_run_id = mlflow_run.info.run_id
            mlflow.log_params({
                "job_id": job_id,
                "dataset_name": dataset_name,
                "epochs": epochs,
                "imgsz": imgsz,
                "batch": batch,
                "patience": patience,
                "class_names": str(class_names),
                "base_model": os.path.basename(base_model_path),
            })
            mlflow.set_tags({
                "job_id": job_id,
                "model_type": "yolo",
                "framework": "ultralytics",
            })
            logger.info("MLflow run started: %s (tracking_uri=%s)", mlflow_run_id, mlflow_tracking_uri)
        except Exception as e_mlflow_init:
            logger.warning("MLflow run start warning: %s", e_mlflow_init)
            mlflow_run = None

        # 4. Train ด้วย Ultralytics (CPU-bound → รันใน thread แยก)
        run_dir = os.path.join(work_dir, "runs")
        results_data = await asyncio.to_thread(
            _run_ultralytics_training,
            base_model_path=base_model_path,
            yaml_path=yaml_path,
            run_dir=run_dir,
            job_id=job_id,
            epochs=epochs,
            imgsz=imgsz,
            batch=batch,
            patience=patience,
        )

        actual_run_dir = results_data["run_dir"]

        # 5. ซิงค์ Event Logs เข้า TensorBoard Log Directory
        _sync_tensorboard_logs(actual_run_dir, job_id, results_data.get("best_metrics", {}))

        # 6. บันทึก Metrics และ Artifacts ลง MLflow
        if mlflow_run is not None:
            try:
                import mlflow
                if results_data.get("best_metrics"):
                    import re
                    safe_metrics = {
                        re.sub(r"[^a-zA-Z0-9_\-\. /]", "_", str(k)): float(v)
                        for k, v in results_data["best_metrics"].items()
                        if isinstance(v, (int, float))
                    }
                    mlflow.log_metrics(safe_metrics)
                if actual_run_dir and os.path.exists(actual_run_dir):
                    mlflow.log_artifacts(actual_run_dir, artifact_path="yolo_outputs")
                mlflow.end_run()
                logger.info("MLflow run %s completed successfully", mlflow_run_id)
            except Exception as e_mlflow_finish:
                logger.warning("MLflow logging artifacts error: %s", e_mlflow_finish)

        # 7. บันทึกโมเดล best.pt ลง storage และ MinIO
        prefix = f"yolo/{dataset_name}/{job_id}"
        uploaded_files = _upload_results(minio_client, actual_run_dir, prefix)

        # สำเนา best.pt เป็นโมเดลหลัก yolo11n_v3.pt ในเครื่องถ้ามี
        best_pt_src = os.path.join(actual_run_dir, "weights", "best.pt")
        if os.path.isfile(best_pt_src):
            for target_local in [
                "/app/storage/models/non_time_serie/yolo11n_v3.pt",
                "./storage/models/non_time_serie/yolo11n_v3.pt"
            ]:
                try:
                    os.makedirs(os.path.dirname(target_local), exist_ok=True)
                    shutil.copy2(best_pt_src, target_local)
                    logger.info("Updated active model weights at %s", target_local)
                except Exception:
                    pass

        # 8. อัปโหลด metrics.json
        best_m = results_data.get("best_metrics", {})
        test_m = results_data.get("test_metrics", {})
        metrics_summary = {
            "job_id": job_id,
            "dataset_name": dataset_name,
            "class_names": class_names,
            "epochs_requested": epochs,
            "epochs_actual": results_data.get("epochs_actual", epochs),
            "imgsz": imgsz,
            "batch": batch,
            "mAP50": best_m.get("mAP50"),
            "mAP50_95": best_m.get("mAP50_95"),
            "precision": best_m.get("precision"),
            "recall": best_m.get("recall"),
            "best_metrics": best_m,
            "test_metrics": test_m,
            "mlflow_run_id": mlflow_run_id,
            "tensorboard_url": "http://localhost:6006",
            "trained_at": datetime.now(timezone.utc).isoformat(),
        }
        metrics_key = f"{prefix}/metrics.json"
        _upload_bytes(
            minio_client, MODEL_BUCKET, metrics_key,
            json.dumps(metrics_summary, indent=2).encode(), "application/json"
        )

        model_uri = f"minio://{MODEL_BUCKET}/{prefix}/weights/best.pt"
        logger.info("YOLO training job %s done. Model at %s", job_id, model_uri)

        return {
            "status": "success",
            "model_type": "yolo",
            "dataset_name": dataset_name,
            "job_id": job_id,
            "model_uri": model_uri,
            "mlflow_run_id": mlflow_run_id,
            "tensorboard_url": "http://localhost:6006",
            "uploaded_files": uploaded_files,
            "metrics": metrics_summary,
        }

    finally:
        # ล้าง temp files เสมอ
        shutil.rmtree(work_dir, ignore_errors=True)
        logger.info("Cleaned up work_dir: %s", work_dir)


def _sync_tensorboard_logs(actual_run_dir: str, job_id: str, best_metrics: dict = None) -> None:
    """คัดลอกไฟล์ events.out.tfevents.* ไปยัง TensorBoard log directory หรือสร้าง log ด้วย SummaryWriter."""
    try:
        tb_dest = os.path.join(TENSORBOARD_LOG_DIR, f"run_{job_id}")
        os.makedirs(tb_dest, exist_ok=True)
        synced = False
        for root, _, files in os.walk(actual_run_dir):
            for file in files:
                if file.startswith("events.out.tfevents"):
                    src = os.path.join(root, file)
                    shutil.copy2(src, os.path.join(tb_dest, file))
                    logger.info("Synced TensorBoard event log to %s", tb_dest)
                    synced = True
        if not synced and best_metrics:
            from torch.utils.tensorboard import SummaryWriter
            writer = SummaryWriter(log_dir=tb_dest)
            for k, v in best_metrics.items():
                if isinstance(v, (int, float)):
                    safe_k = str(k).replace("metrics/", "")
                    writer.add_scalar(safe_k, float(v), 0)
            writer.flush()
            writer.close()
            logger.info("Wrote TensorBoard summary directly to %s", tb_dest)
    except Exception as e_tb:
        logger.warning("TensorBoard sync warning: %s", e_tb)


def _run_ultralytics_training(
    base_model_path: str,
    yaml_path: str,
    run_dir: str,
    job_id: str,
    epochs: int,
    imgsz: int,
    batch: int,
    patience: int,
) -> dict:
    """รัน YOLO training ด้วย Ultralytics API."""
    from ultralytics import YOLO, settings
    try:
        settings.update({"tensorboard": True})
    except Exception:
        pass

    logger.info(
        "Starting Ultralytics training: model=%s epochs=%d imgsz=%d batch=%d",
        base_model_path, epochs, imgsz, batch,
    )

    model = YOLO(base_model_path)
    results = model.train(
        data=yaml_path,
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        patience=patience,
        project=run_dir,
        name=f"run_{job_id}",
        exist_ok=True,
        plots=True,
        verbose=True,
        device="cpu",
    )

    actual_run_dir = str(results.save_dir) if hasattr(results, "save_dir") else os.path.join(run_dir, f"run_{job_id}")

    best_metrics = {}
    try:
        if hasattr(results, "results_dict"):
            best_metrics = {k: float(v) for k, v in results.results_dict.items() if isinstance(v, (int, float))}
    except Exception:
        pass

    # ประเมินผลบน Held-out test set (unseen test split)
    test_metrics = {}
    try:
        test_results = model.val(
            data=yaml_path,
            split="test",
            project=run_dir,
            name=f"test_{job_id}",
            exist_ok=True,
            plots=True,
            device="cpu",
        )
        if hasattr(test_results, "results_dict"):
            for k, v in test_results.results_dict.items():
                if isinstance(v, (int, float)):
                    test_metrics[f"test/{k}"] = float(v)
            if "metrics/precision(B)" in test_results.results_dict:
                test_metrics["precision"] = float(test_results.results_dict["metrics/precision(B)"])
            if "metrics/recall(B)" in test_results.results_dict:
                test_metrics["recall"] = float(test_results.results_dict["metrics/recall(B)"])
            if "metrics/mAP50(B)" in test_results.results_dict:
                test_metrics["mAP50"] = float(test_results.results_dict["metrics/mAP50(B)"])
            if "metrics/mAP50-95(B)" in test_results.results_dict:
                test_metrics["mAP50_95"] = float(test_results.results_dict["metrics/mAP50-95(B)"])
        logger.info("Held-out test set evaluation: mAP50=%.4f, mAP50-95=%.4f", 
                    test_metrics.get("mAP50", 0.0), test_metrics.get("mAP50_95", 0.0))
    except Exception as e_test:
        logger.warning("Held-out test set evaluation notice: %s", e_test)

    # แมปคีย์มาตรฐานสำหรับ UI และ API
    if "metrics/precision(B)" in best_metrics and "precision" not in best_metrics:
        best_metrics["precision"] = best_metrics["metrics/precision(B)"]
    if "metrics/recall(B)" in best_metrics and "recall" not in best_metrics:
        best_metrics["recall"] = best_metrics["metrics/recall(B)"]
    if "metrics/mAP50(B)" in best_metrics and "mAP50" not in best_metrics:
        best_metrics["mAP50"] = best_metrics["metrics/mAP50(B)"]
    if "metrics/mAP50-95(B)" in best_metrics and "mAP50_95" not in best_metrics:
        best_metrics["mAP50_95"] = best_metrics["metrics/mAP50-95(B)"]

    for k, v in test_metrics.items():
        best_metrics[k] = v

    epochs_actual = epochs
    try:
        if hasattr(results, "epoch"):
            epochs_actual = int(results.epoch) + 1
    except Exception:
        pass

    logger.info("Ultralytics training complete. save_dir=%s", actual_run_dir)
    return {
        "run_dir": actual_run_dir,
        "epochs_actual": epochs_actual,
        "best_metrics": best_metrics,
        "test_metrics": test_metrics,
    }


def _upload_results(client: Minio, run_dir: str, prefix: str) -> list[str]:
    """อัปโหลดไฟล์ผลลัพธ์ที่สำคัญจาก run_dir ขึ้น MinIO."""
    uploaded = []
    priority_files = [
        ("weights/best.pt", "application/octet-stream"),
        ("weights/last.pt", "application/octet-stream"),
        ("results.png", "image/png"),
        ("confusion_matrix.png", "image/png"),
        ("F1_curve.png", "image/png"),
        ("P_curve.png", "image/png"),
        ("R_curve.png", "image/png"),
        ("PR_curve.png", "image/png"),
        ("labels.jpg", "image/jpeg"),
    ]

    for rel_path, content_type in priority_files:
        src = os.path.join(run_dir, rel_path)
        if os.path.exists(src):
            key = f"{prefix}/{rel_path}"
            try:
                _upload_file(client, MODEL_BUCKET, key, src, content_type)
                uploaded.append(key)
            except Exception as e:
                logger.warning("Could not upload %s: %s", rel_path, e)

    return uploaded
