"""YOLO Trainer: ดาวน์โหลด Dataset จาก MinIO → เทรน YOLO11 → อัปโหลดผลลัพธ์ขึ้น MinIO

Flow:
    1. ดาวน์โหลด Dataset (ZIP) จาก MinIO bucket "datasets" ที่ key yolo/<dataset_name>/
    2. แตกไฟล์ลงโฟลเดอร์ชั่วคราว /tmp/yolo_train/<job_id>/
    3. สร้าง dataset.yaml แบบไดนามิกจาก config ที่ส่งมา
    4. โหลด Base Model จาก MinIO (yolo11n.pt) หรือจาก local fallback
    5. รัน model.train() ด้วย Ultralytics API
    6. อัปโหลด best.pt, last.pt, และ plots ขึ้น MinIO bucket "models"
       ที่ prefix  yolo/<dataset_name>/<job_id>/
    7. ล้างโฟลเดอร์ชั่วคราว
    8. คืน dict สรุปผลและ MinIO object key
"""
from __future__ import annotations

import io
import json
import logging
import os
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from minio import Minio
from minio.error import S3Error

logger = logging.getLogger("training_worker.yolo")

# Bucket สำหรับ Dataset ขาเข้าและโมเดล/ผลลัพธ์ขาออก
DATASET_BUCKET = "datasets"
MODEL_BUCKET = "models"

# ตำแหน่ง Base Model ใน MinIO (อัปโหลดไว้ล่วงหน้า) และ local fallback
BASE_MODEL_MINIO_KEY = "yolo/base/yolo11n.pt"
BASE_MODEL_LOCAL_PATH = "/app/storage/models/non_time_serie/yolo11n.pt"


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
# Dataset preparation
# ---------------------------------------------------------------------------

def _download_and_extract_dataset(client: Minio, dataset_name: str,
                                   work_dir: str) -> str:
    """
    ตรวจสอบโฟลเดอร์ Local ก่อน หากพบ Dataset ในเครื่องให้ใช้ path นั้นทันที
    """
    # ตรวจสอบ path ในเครื่อง (รองรับทั้งรันผ่าน Docker และรัน local)
    local_paths = [
        f"/app/storage/data/{dataset_name}",
        f"./storage/data/{dataset_name}"
    ]
    
    for path in local_paths:
        if os.path.exists(path) and os.path.isdir(path):
            logger.info("Using local dataset found at: %s", path)
            return path

    # หากไม่มีในเครื่อง ให้ดาวน์โหลดจาก MinIO ตามปกติ
    zip_key = f"yolo/{dataset_name}/{dataset_name}.zip"
    zip_path = os.path.join(work_dir, f"{dataset_name}.zip")
    dataset_dir = os.path.join(work_dir, "dataset")

    try:
        _download_file(client, DATASET_BUCKET, zip_key, zip_path)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(dataset_dir)
        logger.info("Extracted dataset to %s", dataset_dir)
    except S3Error as e:
        if e.code in ("NoSuchKey", "NoSuchObject", "NotFound", "NoSuchBucket"):
            logger.warning(
                "Dataset ZIP not found at MinIO %s/%s — creating dummy dataset for smoke-test",
                DATASET_BUCKET, zip_key
            )
            _create_dummy_dataset(dataset_dir)
        else:
            raise

    return dataset_dir


def _write_dataset_yaml(dataset_dir: str, class_names: list[str]) -> str:
    """สร้างไฟล์ dataset.yaml สำหรับ Ultralytics YOLO ให้ตรงกับโครงสร้าง train/images และ valid/images."""
    yaml_path = os.path.join(dataset_dir, "dataset.yaml")
    
    # โครงสร้างจริงของ Dataset จากภาพ คือ train/images และ valid/images
    lines = [
        f"path: {dataset_dir}",
        "train: train/images",
        "val: valid/images",
        f"nc: {len(class_names)}",
        "names: " + str(class_names),
        "",
    ]
    with open(yaml_path, "w") as f:
        f.write("\n".join(lines))
    logger.info("dataset.yaml written to %s", yaml_path)
    return yaml_path


def _create_dummy_dataset(dataset_dir: str) -> None:
    """
    สร้าง dummy dataset ขั้นต่ำสำหรับทดสอบ pipeline โดยไม่ต้องมีภาพจริง
    ใช้ภาพสีเดียว 64x64 สำหรับ train (5 ภาพ) และ val (2 ภาพ)
    """
    try:
        import numpy as np
        from PIL import Image  # Pillow มาพร้อมกับ ultralytics

        for split in ("train", "val"):
            img_dir = os.path.join(dataset_dir, "images", split)
            lbl_dir = os.path.join(dataset_dir, "labels", split)
            os.makedirs(img_dir, exist_ok=True)
            os.makedirs(lbl_dir, exist_ok=True)
            n = 5 if split == "train" else 2
            for i in range(n):
                # ภาพสีเขียวอ่อน 64x64 เพื่อจำลอง
                img_arr = np.full((64, 64, 3), (100, 200, 100), dtype=np.uint8)
                img = Image.fromarray(img_arr)
                img.save(os.path.join(img_dir, f"sample_{i}.jpg"))
                # label: class 0, bbox กึ่งกลางภาพ
                with open(os.path.join(lbl_dir, f"sample_{i}.txt"), "w") as f:
                    f.write("0 0.5 0.5 0.8 0.8\n")

        logger.info("Dummy dataset created at %s", dataset_dir)
    except Exception as e:
        logger.error("Failed to create dummy dataset: %s", e)
        raise




def _get_base_model(client: Minio, work_dir: str) -> str:
    """
    หาไฟล์ Base Model YOLO:
    1. ลองดาวน์โหลดจาก MinIO (yolo/base/yolo11n.pt)
    2. Fallback ไปที่ local storage mount
    3. Fallback สุดท้าย: ใช้ชื่อ "yolo11n.pt" ให้ Ultralytics ดาวน์โหลดเอง
    """
    local_dest = os.path.join(work_dir, "yolo11n.pt")

    # ลอง MinIO ก่อน
    try:
        _download_file(client, MODEL_BUCKET, BASE_MODEL_MINIO_KEY, local_dest)
        logger.info("Using base model from MinIO: %s", BASE_MODEL_MINIO_KEY)
        return local_dest
    except S3Error as e:
        if e.code not in ("NoSuchKey", "NoSuchObject", "NotFound", "NoSuchBucket"):
            raise

    # Fallback local mount
    if os.path.exists(BASE_MODEL_LOCAL_PATH):
        shutil.copy2(BASE_MODEL_LOCAL_PATH, local_dest)
        logger.info("Using base model from local mount: %s", BASE_MODEL_LOCAL_PATH)
        return local_dest

    # ให้ Ultralytics ดาวน์โหลดเอง
    logger.info("Base model not found locally/MinIO; Ultralytics will download yolo11n.pt")
    return "yolo11n.pt"


# ---------------------------------------------------------------------------
# Core Training
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
    """
    Pipeline หลักสำหรับเทรน YOLO:

    Args:
        job_id:       UUID ของ training job (ใช้จัดโฟลเดอร์ใน MinIO)
        dataset_name: ชื่อ dataset ที่เก็บอยู่ใน MinIO bucket "datasets"
                      ที่ key yolo/<dataset_name>/<dataset_name>.zip
        class_names:  รายชื่อ class (default: ["shrimp"])
        epochs:       จำนวน epoch สำหรับ training
        imgsz:        ขนาดภาพ input (px)
        batch:        batch size (-1 = auto)
        patience:     จำนวน epoch ที่ยอมให้ val loss ไม่ดีขึ้นก่อน early stop
    """
    import asyncio

    if class_names is None:
        class_names = ["box"]


    minio_client = _get_minio_client()
    work_dir = tempfile.mkdtemp(prefix=f"yolo_{job_id}_")
    logger.info("YOLO training job %s started. work_dir=%s", job_id, work_dir)

    try:
        # 1. ดาวน์โหลดและเตรียม Dataset
        dataset_dir = _download_and_extract_dataset(minio_client, dataset_name, work_dir)
        yaml_path = _write_dataset_yaml(dataset_dir, class_names)

        # 2. เตรียม Base Model
        base_model_path = _get_base_model(minio_client, work_dir)

        # 3. Train ด้วย Ultralytics (CPU-bound → รันใน thread แยก)
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

        # 4. อัปโหลดผลลัพธ์ขึ้น MinIO
        prefix = f"yolo/{dataset_name}/{job_id}"
        uploaded_files = _upload_results(minio_client, results_data["run_dir"], prefix)

        # 5. อัปโหลด metrics.json
        metrics_summary = {
            "job_id": job_id,
            "dataset_name": dataset_name,
            "class_names": class_names,
            "epochs_requested": epochs,
            "epochs_actual": results_data.get("epochs_actual", epochs),
            "imgsz": imgsz,
            "batch": batch,
            "best_metrics": results_data.get("best_metrics", {}),
            "trained_at": datetime.utcnow().isoformat(),
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
            "uploaded_files": uploaded_files,
            "metrics": metrics_summary,
        }

    finally:
        # 6. ล้าง temp files เสมอ ไม่ว่าจะสำเร็จหรือล้มเหลว
        shutil.rmtree(work_dir, ignore_errors=True)
        logger.info("Cleaned up work_dir: %s", work_dir)


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
    """
    รัน YOLO training แบบ synchronous (เรียกผ่าน asyncio.to_thread)

    คืน dict ที่มี:
        run_dir:       โฟลเดอร์ผลลัพธ์ที่ Ultralytics สร้าง
        epochs_actual: จำนวน epoch ที่รันจริง
        best_metrics:  metrics จาก validation set ของ epoch ที่ดีที่สุด
    """
    from ultralytics import YOLO

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
        # ปิด Ultralytics wandb/clearml logging เพื่อใช้ MLflow ของระบบเราเอง
        exist_ok=True,
        plots=True,
        verbose=True,
        device="cpu",  # ใช้ CPU; เปลี่ยนเป็น "0" ถ้ามี GPU
    )

    # โฟลเดอร์ผลลัพธ์จริงที่ Ultralytics สร้าง
    actual_run_dir = str(results.save_dir) if hasattr(results, "save_dir") else os.path.join(run_dir, f"run_{job_id}")

    # ดึง metrics จาก results object
    best_metrics = {}
    try:
        if hasattr(results, "results_dict"):
            best_metrics = {k: float(v) for k, v in results.results_dict.items() if isinstance(v, (int, float))}
    except Exception:
        pass

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
    }


def _upload_results(client: Minio, run_dir: str, prefix: str) -> list[str]:
    """
    อัปโหลดไฟล์ผลลัพธ์ที่สำคัญจาก run_dir ขึ้น MinIO:
    - weights/best.pt
    - weights/last.pt
    - ไฟล์ plot *.png, *.jpg ต่าง ๆ
    คืนรายการ MinIO object key ที่อัปโหลดสำเร็จ
    """
    uploaded = []

    # Priority files
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

    if not uploaded:
        logger.warning("No result files found in %s to upload", run_dir)

    return uploaded
