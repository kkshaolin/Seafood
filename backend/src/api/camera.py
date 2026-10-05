"""Camera API Router for Live Camera View with YOLO Bounding Box Detection.

Provides periodic (1 minute / 60s) snapshot frame inference with real YOLO bbox detection,
caching the result to minimize CPU/GPU usage while providing live monitoring.
"""

import io
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from ultralytics import YOLO

from db.database import get_db_session
from models.stock import BoxLog

logger = logging.getLogger("api_camera")
router = APIRouter(prefix="/camera", tags=["camera"])

# In-memory cache for 60 seconds (1 minute interval)
# Structure: camera_id -> (timestamp, jpeg_bytes, metadata_dict)
_FRAME_CACHE: Dict[str, Tuple[float, bytes, dict]] = {}
CACHE_TTL_SECONDS = 60

_YOLO_MODEL: Optional[YOLO] = None


def get_yolo_model() -> YOLO:
    """Load and cache the YOLO model instance."""
    global _YOLO_MODEL
    if _YOLO_MODEL is not None:
        return _YOLO_MODEL

    candidates = [
        Path("/app/storage/models/non_time_serie/yolo11n.pt"),
        Path("storage/models/non_time_serie/yolo11n.pt"),
        Path("/tmp/best.pt"),
    ]
    for p in candidates:
        if p.is_file():
            try:
                logger.info("Loading YOLO model from %s", p)
                model = YOLO(str(p))
                if 28 in model.names and model.names[28] == "suitcase":
                    model.names[28] = "box"
                _YOLO_MODEL = model
                return _YOLO_MODEL
            except Exception as e:
                logger.warning("Could not load YOLO from %s: %s", p, e)

    logger.info("Loading default yolo11n.pt model...")
    model = YOLO("yolo11n.pt")
    if 28 in model.names and model.names[28] == "suitcase":
        model.names[28] = "box"
    _YOLO_MODEL = model
    return _YOLO_MODEL


def get_video_path(camera_id: str) -> Path:
    """Resolve mock video file for the given camera ID."""
    cid = camera_id.lower()
    filename = "mockA.mp4" if ("main" in cid or cid.endswith("a") or "_a" in cid or "zonea" in cid) else "mockB.mp4"
    candidates = [
        Path("/app/storage/data/videos") / filename,
        Path("storage/data/videos") / filename,
        Path(__file__).resolve().parents[3] / "storage" / "data" / "videos" / filename,
        Path("/app/frontend/public") / filename,
        Path("frontend/public") / filename,
    ]
    for p in candidates:
        if p.is_file():
            return p
    raise FileNotFoundError(f"Video file {filename} not found in candidate paths")


def extract_annotated_frame(camera_id: str) -> Tuple[bytes, dict]:
    """Extract a frame from the video, run real YOLO inference, and return the annotated JPEG."""
    video_path = get_video_path(camera_id)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video file: {video_path}")

    try:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        target_idx = 0
        if total_frames > 5:
            # Shift frame based on current 10-second block to reflect progression over time
            target_idx = (int(time.time() / 10) * 15) % max(1, total_frames - 1)
            cap.set(cv2.CAP_PROP_POS_FRAMES, target_idx)

        ret, frame = cap.read()
        if not ret or frame is None:
            raise RuntimeError(f"Failed to read frame from {video_path}")

        # Run real YOLO inference
        model = get_yolo_model()
        res = model.predict(frame, conf=0.015, verbose=False)
        boxes = res[0].boxes

        # Plot real BBoxes directly using Ultralytics
        annotated_frame = res[0].plot(labels=True, conf=True)

        box_count = len(boxes)
        avg_conf = float(boxes.conf.mean()) if box_count > 0 else 0.0

        # Encode to JPEG
        success, buffer = cv2.imencode(".jpg", annotated_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
        if not success:
            raise RuntimeError("Failed to encode annotated frame to JPEG")

        jpeg_bytes = buffer.tobytes()
        meta = {
            "camera_id": camera_id,
            "detected_boxes": box_count,
            "confidence": round(avg_conf, 3),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "frame_idx": target_idx,
            "model_name": "YOLO11",
            "interval_seconds": CACHE_TTL_SECONDS
        }
        return jpeg_bytes, meta
    finally:
        cap.release()


@router.get("/{camera_id}/frame", summary="ดึงภาพ Snapshot พร้อม BBox จริงจากโมเดล YOLO (อัปเดตทุก 1 นาที)")
async def get_camera_annotated_frame(camera_id: str, force: bool = Query(False, description="บังคับให้อนุมานภาพใหม่ทันที")):
    """ส่งคืนรูปภาพ JPEG พร้อมผลการตรวจจับ BBox จริงจากโมเดล YOLO โดยแคชไว้ 60 วินาที เพื่อประหยัดทรัพยากร."""
    now = time.time()
    if not force and camera_id in _FRAME_CACHE:
        cached_time, cached_bytes, _ = _FRAME_CACHE[camera_id]
        if now - cached_time < CACHE_TTL_SECONDS:
            return Response(
                content=cached_bytes,
                media_type="image/jpeg",
                headers={
                    "Cache-Control": f"public, max-age={int(CACHE_TTL_SECONDS - (now - cached_time))}",
                    "X-Cache": "HIT"
                }
            )

    try:
        jpeg_bytes, meta = extract_annotated_frame(camera_id)
        _FRAME_CACHE[camera_id] = (now, jpeg_bytes, meta)
        return Response(
            content=jpeg_bytes,
            media_type="image/jpeg",
            headers={
                "Cache-Control": f"public, max-age={CACHE_TTL_SECONDS}",
                "X-Cache": "MISS",
                "X-Detected-Boxes": str(meta["detected_boxes"])
            }
        )
    except Exception as e:
        logger.error("Failed to generate annotated frame for %s: %s", camera_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Frame inference error: {str(e)}")


@router.get("/{camera_id}/latest", summary="ดึงข้อมูลสรุปการตรวจจับล่าสุดของกล้อง")
async def get_latest_camera_log(camera_id: str, session: AsyncSession = Depends(get_db_session)):
    """ส่งคืน metadata การตรวจจับล่าสุดของกล้องที่เลือก พร้อมเวลาอัปเดตครั้งถัดไป."""
    now = time.time()
    meta = None
    if camera_id in _FRAME_CACHE:
        cached_time, _, meta = _FRAME_CACHE[camera_id]
        elapsed = now - cached_time
        next_update = max(0, int(CACHE_TTL_SECONDS - elapsed))
    else:
        # Pre-warm cache if not present
        try:
            jpeg_bytes, meta = extract_annotated_frame(camera_id)
            _FRAME_CACHE[camera_id] = (now, jpeg_bytes, meta)
            next_update = CACHE_TTL_SECONDS
        except Exception:
            next_update = 0

    # Also query DB for historical box log
    cid = camera_id.lower()
    zone_code = "ZoneA" if ("main" in cid or cid.endswith("a") or "_a" in cid or "zonea" in cid) else "ZoneB"
    stmt = select(BoxLog).order_by(desc(BoxLog.time)).limit(1)
    res = await session.execute(stmt)
    latest_db = res.scalar_one_or_none()

    return {
        "camera_id": camera_id,
        "zone": zone_code,
        "detected_boxes": meta.get("detected_boxes", 0) if meta else (latest_db.boxes_A if zone_code == "ZoneA" and latest_db else (latest_db.boxes_B if latest_db else 0)),
        "confidence": meta.get("confidence", 0.0) if meta else (latest_db.confidence if latest_db else 0.0),
        "last_updated": meta.get("timestamp") if meta else (latest_db.time.isoformat() if latest_db else datetime.now(timezone.utc).isoformat()),
        "next_update_seconds": next_update,
        "interval_seconds": CACHE_TTL_SECONDS,
        "status": "online"
    }


@router.get("/{camera_id}/logs", summary="ดึงประวัติการตรวจนับกล่องจากกล้อง")
async def get_camera_logs_history(camera_id: str, limit: int = 10, session: AsyncSession = Depends(get_db_session)):
    """ดึงข้อมูลประวัติ box logs ที่สัมพันธ์กับกล้องที่เลือก."""
    try:
        stmt = select(BoxLog).order_by(desc(BoxLog.time)).limit(limit)
        res = await session.execute(stmt)
        logs = res.scalars().all()
        return {
            "camera_id": camera_id,
            "logs": [
                {
                    "id": l.id,
                    "time": l.time.isoformat(),
                    "product": l.product,
                    "boxes": l.boxes_A if "main" in camera_id.lower() else l.boxes_B,
                    "total_boxes": l.total_boxes,
                    "confidence": l.confidence
                }
                for l in logs
            ]
        }
    except Exception as e:
        logger.error("Failed to fetch camera logs: %s", e)
        return {"camera_id": camera_id, "logs": []}
