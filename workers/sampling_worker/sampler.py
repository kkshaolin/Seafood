"""Camera Sampling Service (Sampling Worker).

Captures raw/cropped frames from Zone A (mockA.mp4) and Zone B (mockB.mp4)
mock videos located strictly in 'frontend/public/', and uploads them to MinIO
bucket 'sampling-camera' under 'ZoneA/' and 'ZoneB/'.
"""

import io
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

import cv2
from minio import Minio

logger = logging.getLogger("sampling_worker.sampler")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s"))
    logger.addHandler(_handler)

# MinIO Config
MINIO_BUCKET = os.getenv("SAMPLING_BUCKET", "sampling-camera")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "admin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "password123")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"


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


def find_video_path(zone_suffix: str) -> Path:
    """Locate mock video for Zone A (mockA.mp4) or Zone B (mockB.mp4) strictly from frontend/public/."""
    filename = f"mock{zone_suffix.upper()}.mp4"
    candidates = [
        Path(__file__).resolve().parents[2] / "frontend" / "public" / filename,
        Path("frontend/public") / filename,
        Path("/app/frontend/public") / filename,
        Path("/frontend/public") / filename,
    ]
    for p in candidates:
        if p.is_file():
            return p
    raise FileNotFoundError(f"Mock video {filename} not found in frontend/public/: {[str(c) for c in candidates]}")


def extract_and_crop_frame(
    video_path: Path,
    crop: bool = True,
    target_frame_idx: Optional[int] = None,
    video_time: Optional[float] = None,
    predict_timestamp: Optional[float] = None,
) -> bytes:
    """Reads a specific frame from video at the moment predict was requested, crops it, and returns encoded JPEG bytes."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video file: {video_path}")

    try:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        if total_frames > 0:
            if target_frame_idx is not None:
                target_idx = int(target_frame_idx) % total_frames
            elif video_time is not None:
                target_idx = int(video_time * fps) % total_frames
            else:
                # เฟรม ณ วินาทีที่กด Predict (คำนวณตาม timestamp ขณะกด)
                current_time = predict_timestamp if predict_timestamp is not None else datetime.now(timezone.utc).timestamp()
                target_idx = int((current_time * fps) % total_frames)
            cap.set(cv2.CAP_PROP_POS_FRAMES, target_idx)

        ret, frame = cap.read()
        if not ret or frame is None:
            raise RuntimeError(f"Failed to read frame from video: {video_path}")

        h, w = frame.shape[:2]
        if crop:
            # Crop center detection area (84% height, 84% width)
            y_start = int(h * 0.08)
            y_end = int(h * 0.92)
            x_start = int(w * 0.08)
            x_end = int(w * 0.92)
            processed_frame = frame[y_start:y_end, x_start:x_end]
        else:
            processed_frame = frame

        # Encode to JPEG
        success, buffer = cv2.imencode(".jpg", processed_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        if not success:
            raise RuntimeError("Failed to encode cropped frame to JPEG")

        return buffer.tobytes()
    finally:
        cap.release()


def get_latest_sampled_frame_keys(
    client: Optional[Minio] = None,
    bucket_name: Optional[str] = None
) -> Tuple[Optional[str], Optional[str]]:
    """Query MinIO bucket 'sampling-camera' to find the latest frame keys for Zone A and Zone B."""
    if client is None:
        client = get_minio_client()
    b_name = bucket_name or MINIO_BUCKET

    if not client.bucket_exists(b_name):
        return None, None

    def _get_latest_key(prefix: str) -> Optional[str]:
        objs = list(client.list_objects(b_name, prefix=prefix, recursive=True))
        if not objs:
            return None
        # Sort by object_name descending (keys are formatted as ZoneX/frame_YYYYMMDD_HHMMSS_ffffff.jpg)
        objs.sort(key=lambda o: o.object_name, reverse=True)
        return objs[0].object_name

    return _get_latest_key("ZoneA/"), _get_latest_key("ZoneB/")


async def sample_camera_frames(
    crop: bool = True,
    record_db: bool = False,
    video_time: Optional[float] = None,
    video_time_a: Optional[float] = None,
    video_time_b: Optional[float] = None,
    predict_timestamp: Optional[float] = None,
) -> dict:
    """Capture frames from frontend/public mock videos at the predict moment and upload raw frames to MinIO 'sampling-camera'."""
    client = get_minio_client()
    ensure_bucket(client, MINIO_BUCKET)

    now = datetime.now(timezone.utc)
    ts = predict_timestamp if predict_timestamp is not None else now.timestamp()
    timestamp_str = now.strftime("%Y%m%d_%H%M%S_%f")

    # 1. Process Zone A (mockA.mp4 from frontend/public)
    v_time_a = video_time_a if video_time_a is not None else video_time
    video_a_path = find_video_path("A")
    jpeg_bytes_a = extract_and_crop_frame(
        video_a_path, crop=crop, video_time=v_time_a, predict_timestamp=ts
    )
    zone_a_key = f"ZoneA/frame_{timestamp_str}.jpg"
    client.put_object(
        bucket_name=MINIO_BUCKET,
        object_name=zone_a_key,
        data=io.BytesIO(jpeg_bytes_a),
        length=len(jpeg_bytes_a),
        content_type="image/jpeg",
    )
    logger.info("Uploaded sampled Zone A frame to MinIO: %s/%s (%d bytes)", MINIO_BUCKET, zone_a_key, len(jpeg_bytes_a))

    # 2. Process Zone B (mockB.mp4 from frontend/public)
    v_time_b = video_time_b if video_time_b is not None else video_time
    video_b_path = find_video_path("B")
    jpeg_bytes_b = extract_and_crop_frame(
        video_b_path, crop=crop, video_time=v_time_b, predict_timestamp=ts
    )
    zone_b_key = f"ZoneB/frame_{timestamp_str}.jpg"
    client.put_object(
        bucket_name=MINIO_BUCKET,
        object_name=zone_b_key,
        data=io.BytesIO(jpeg_bytes_b),
        length=len(jpeg_bytes_b),
        content_type="image/jpeg",
    )
    logger.info("Uploaded sampled Zone B frame to MinIO: %s/%s (%d bytes)", MINIO_BUCKET, zone_b_key, len(jpeg_bytes_b))

    return {
        "status": "success",
        "bucket": MINIO_BUCKET,
        "zone_a_key": zone_a_key,
        "zone_b_key": zone_b_key,
        "timestamp": now.isoformat(),
    }
