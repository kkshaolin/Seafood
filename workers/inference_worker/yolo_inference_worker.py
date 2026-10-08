"""YOLO Inference Worker & Database Sync Service.

Responsibilities:
1. Pulls latest raw/cropped camera frames from MinIO bucket 'sampling-camera' (Zone A and Zone B).
2. Runs trained YOLO model to detect boxes and draws bounding boxes (BBoxes).
3. Uploads the annotated frames (with BBoxes) to MinIO bucket 'result-yolo'.
4. Records camera detection results (both cameras) into PostgreSQL 'box_logs'
   and syncs stock values into 'daily_inventories' and 'monthly_inventories'.
"""

import io
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np
from minio import Minio

logger = logging.getLogger("inference_worker.yolo")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s"))
    logger.addHandler(_handler)

# MinIO Config
SAMPLING_BUCKET = os.getenv("SAMPLING_BUCKET", "sampling-camera")
RESULT_YOLO_BUCKET = os.getenv("RESULT_YOLO_BUCKET", "result-yolo")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "admin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "password123")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

_YOLO_MODEL = None


def get_minio_client() -> Minio:
    return Minio(
        endpoint=MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE,
    )


def ensure_bucket(client: Minio, bucket_name: str) -> None:
    if not client.bucket_exists(bucket_name):
        client.make_bucket(bucket_name)
        logger.info("Created MinIO bucket: %s", bucket_name)


def load_yolo_model():
    """Load trained YOLO model (singleton). Prioritizes yolo11n_v3.pt."""
    global _YOLO_MODEL
    if _YOLO_MODEL is not None:
        return _YOLO_MODEL

    from ultralytics import YOLO

    candidates = [
        Path("/tmp/best.pt"),
        Path("/app/storage/models/non_time_serie/yolo11n_v3.pt"),
        Path("storage/models/non_time_serie/yolo11n_v3.pt"),
        Path(__file__).resolve().parents[2] / "storage" / "models" / "non_time_serie" / "yolo11n_v3.pt",
        Path("/app/storage/models/non_time_serie/yolo11n.pt"),
        Path("storage/models/non_time_serie/yolo11n.pt"),
        Path(__file__).resolve().parents[2] / "storage" / "models" / "non_time_serie" / "yolo11n.pt",
    ]
    for p in candidates:
        if p.is_file():
            try:
                logger.info("Loading YOLO model from: %s", p)
                model = YOLO(str(p))
                class_names = list(model.names.values()) if hasattr(model, "names") else []
                if any("box" in name.lower() for name in class_names):
                    logger.info("Verified box detection model (%s) with classes: %s", p.name, model.names)
                    _YOLO_MODEL = model
                    return _YOLO_MODEL
                else:
                    logger.warning("Model %s does not contain box class: %s", p, model.names)
            except Exception as e:
                logger.warning("Could not load YOLO from %s: %s", p, e)

    raise FileNotFoundError(
        "Trained box detection model not found or invalid! "
        "Expected yolo11n_v3.pt at storage/models/non_time_serie/yolo11n_v3.pt."
    )


def detect_boxes_with_yolo(jpeg_bytes: bytes, zone: str) -> Tuple[int, float, bytes]:
    """Run YOLO inference and return the count, confidence, and annotated frame with BBoxes."""
    try:
        model = load_yolo_model()
        nparr = np.frombuffer(jpeg_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError(f"Failed to decode JPEG bytes for Zone {zone} YOLO inference")

        results = model.predict(img, conf=0.15, verbose=False)
        boxes = results[0].boxes
        det_count = len(boxes)

        if det_count > 0:
            avg_conf = float(boxes.conf.mean())
            final_count = det_count
        else:
            final_count = 0
            avg_conf = 0.0

        annotated_frame = results[0].plot(labels=True, conf=True)
        success, buffer = cv2.imencode(
            ".jpg", annotated_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90]
        )
        if not success:
            raise RuntimeError(f"Failed to encode annotated frame with BBoxes for Zone {zone}")

        logger.info("YOLO detected %d boxes in Zone %s (conf=%.2f)", final_count, zone, avg_conf)
        return final_count, avg_conf, buffer.tobytes()
    except Exception as e:
        logger.error("YOLO detection encountered error: %s", e)
        raise


def get_latest_sampling_key(client: Minio, prefix: str) -> Optional[str]:
    """Retrieve the latest frame object key from 'sampling-camera' bucket under the given prefix."""
    if not client.bucket_exists(SAMPLING_BUCKET):
        return None
    objs = list(client.list_objects(SAMPLING_BUCKET, prefix=prefix, recursive=True))
    if not objs:
        return None
    objs.sort(key=lambda o: o.object_name, reverse=True)
    return objs[0].object_name


async def record_box_log_and_sync_inventory(
    now: datetime,
    zone_a_key: str,
    zone_b_key: str,
    boxes_a: int,
    boxes_b: int,
    confidence: float = 0.95,
) -> None:
    """Insert detection log into PostgreSQL 'box_logs' and sync with daily & monthly inventory tables."""
    import asyncpg
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://admin:secretpassword@postgres:5432/my_database"
    )
    clean_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(clean_url)
    try:
        total = boxes_a + boxes_b
        image_summary = f"{zone_a_key};{zone_b_key}"
        product_name = "Frozen Shrimp"
        today_date = now.date()

        # 1. Insert into box_logs
        await conn.execute(
            """
            INSERT INTO box_logs (time, product, boxes_a, boxes_b, total_boxes, camera_id, image_path, confidence, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9);
            """,
            now,
            product_name,
            boxes_a,
            boxes_b,
            total,
            "cam_main,cam_dock",
            image_summary,
            float(confidence),
            now
        )
        logger.info("Recorded YOLO detection to box_logs: ZoneA=%d, ZoneB=%d, Total=%d", boxes_a, boxes_b, total)

        # 2. Sync to daily_inventories (upsert for today)
        await conn.execute(
            """
            INSERT INTO daily_inventories (time, product, boxes_a, boxes_b, total_boxes, inbound_boxes, outbound_boxes, created_at)
            VALUES ($1, $2, $3, $4, $5, 0, 0, $6)
            ON CONFLICT (time, product) DO UPDATE SET
                boxes_a = EXCLUDED.boxes_a,
                boxes_b = EXCLUDED.boxes_b,
                total_boxes = EXCLUDED.total_boxes,
                created_at = EXCLUDED.created_at;
            """,
            today_date,
            product_name,
            boxes_a,
            boxes_b,
            total,
            now
        )
        logger.info("Synced YOLO detection to daily_inventories for %s (total=%d)", today_date, total)
        # Note: monthly_inventories is reserved strictly for official closed monthly totals and not overwritten by instantaneous camera counts.
    finally:
        await conn.close()


async def run_yolo_detection_from_sampling(
    zone_a_key: Optional[str] = None,
    zone_b_key: Optional[str] = None,
    record_db: bool = True,
) -> dict:
    """Fetch latest frames from MinIO 'sampling-camera', detect boxes with YOLO,

    upload annotated frames with BBoxes to MinIO 'result-yolo',
    and record both cameras' box counts in PostgreSQL.
    """
    client = get_minio_client()
    ensure_bucket(client, SAMPLING_BUCKET)
    ensure_bucket(client, RESULT_YOLO_BUCKET)

    now = datetime.now(timezone.utc)
    timestamp_str = now.strftime("%Y%m%d_%H%M%S_%f")

    # 1. Resolve source keys from 'sampling-camera'
    source_key_a = zone_a_key or get_latest_sampling_key(client, "ZoneA/")
    source_key_b = zone_b_key or get_latest_sampling_key(client, "ZoneB/")

    if not source_key_a or not source_key_b:
        # Fallback: trigger sampling once if no frames exist yet in sampling-camera
        logger.info("No existing frames found in '%s', triggering sampling now...", SAMPLING_BUCKET)
        from sampling_worker.sampler import sample_camera_frames
        fresh_sample = await sample_camera_frames(crop=True)
        source_key_a = source_key_a or fresh_sample["zone_a_key"]
        source_key_b = source_key_b or fresh_sample["zone_b_key"]

    logger.info("Pulling latest frames from MinIO '%s': ZoneA=%s, ZoneB=%s", SAMPLING_BUCKET, source_key_a, source_key_b)

    # 2. Download raw frames from sampling-camera
    resp_a = client.get_object(SAMPLING_BUCKET, source_key_a)
    jpeg_bytes_a = resp_a.read()
    resp_a.close()
    resp_a.release_conn()

    resp_b = client.get_object(SAMPLING_BUCKET, source_key_b)
    jpeg_bytes_b = resp_b.read()
    resp_b.close()
    resp_b.release_conn()

    # 3. Run YOLO detection on Zone A
    boxes_a, conf_a, annotated_bytes_a = detect_boxes_with_yolo(jpeg_bytes_a, "A")
    res_zone_a_key = f"ZoneA/frame_{timestamp_str}.jpg"
    client.put_object(
        bucket_name=RESULT_YOLO_BUCKET,
        object_name=res_zone_a_key,
        data=io.BytesIO(annotated_bytes_a),
        length=len(annotated_bytes_a),
        content_type="image/jpeg",
    )
    logger.info("Saved Zone A annotated frame with BBox to '%s/%s'", RESULT_YOLO_BUCKET, res_zone_a_key)

    # 4. Run YOLO detection on Zone B
    boxes_b, conf_b, annotated_bytes_b = detect_boxes_with_yolo(jpeg_bytes_b, "B")
    res_zone_b_key = f"ZoneB/frame_{timestamp_str}.jpg"
    client.put_object(
        bucket_name=RESULT_YOLO_BUCKET,
        object_name=res_zone_b_key,
        data=io.BytesIO(annotated_bytes_b),
        length=len(annotated_bytes_b),
        content_type="image/jpeg",
    )
    logger.info("Saved Zone B annotated frame with BBox to '%s/%s'", RESULT_YOLO_BUCKET, res_zone_b_key)

    # 5. Summarize detection metrics
    total_boxes = boxes_a + boxes_b
    avg_conf = (conf_a + conf_b) / 2.0

    # 6. Record both cameras to PostgreSQL
    if record_db:
        await record_box_log_and_sync_inventory(
            now=now,
            zone_a_key=res_zone_a_key,
            zone_b_key=res_zone_b_key,
            boxes_a=boxes_a,
            boxes_b=boxes_b,
            confidence=avg_conf,
        )

    return {
        "status": "success",
        "source_bucket": SAMPLING_BUCKET,
        "result_bucket": RESULT_YOLO_BUCKET,
        "zone_a_key": res_zone_a_key,
        "zone_b_key": res_zone_b_key,
        "boxes_A": boxes_a,
        "boxes_B": boxes_b,
        "total_boxes": total_boxes,
        "confidence": avg_conf,
        "timestamp": now.isoformat(),
    }