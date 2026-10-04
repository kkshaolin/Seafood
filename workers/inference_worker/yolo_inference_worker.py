"""YOLO Inference Worker: ดึงภาพจาก MinIO มาให้โมเดล YOLO ทำนายผล นับจำนวนกล่อง และบันทึกลง PostgreSQL."""

import os
import logging
import tempfile
from datetime import datetime
from pathlib import Path

from minio import Minio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import insert
from ultralytics import YOLO

from db.database import SessionLocal
from models.stock import InventorySummary

logger = logging.getLogger("inference_worker.yolo")

DATASET_BUCKET = "datasets"
MODEL_BUCKET = "models"


def _get_minio_client() -> Minio:
    """สร้าง MinIO client จาก environment variables."""
    return Minio(
        endpoint=os.getenv("MINIO_ENDPOINT", "minio:9000"),
        access_key=os.getenv("MINIO_ACCESS_KEY", "admin"),
        secret_key=os.getenv("MINIO_SECRET_KEY", "password123"),
        secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
    )


async def run_yolo_inference(image_key: str, dataset_name: str, job_id: str) -> dict:
    """
    1. ดาวน์โหลดภาพเป้าหมายจาก MinIO bucket "datasets"
    2. ดาวน์โหลดโมเดลน้ำหนัก best.pt จาก MinIO bucket "models"
    3. รัน YOLO Inference เพื่อตรวจจับและนับจำนวนกล่อง แยกตามระดับชั้นวาง (Level 1-4)
    4. บันทึกผลลัพธ์ลงตาราง inventory_summaries ใน PostgreSQL
    """
    minio_client = _get_minio_client()
    
    with tempfile.TemporaryDirectory() as temp_dir:
        local_img_path = os.path.join(temp_dir, "target_image.jpg")
        model_path = os.path.join(temp_dir, "best.pt")
        
        logger.info("Downloading image from MinIO: %s/%s", DATASET_BUCKET, image_key)
        minio_client.fget_object(DATASET_BUCKET, image_key, local_img_path)

        # ดึงไฟล์โมเดล best.pt จากผลการเทรนในข้อ 3
        model_key = f"yolo/{dataset_name}/{job_id}/weights/best.pt"
        logger.info("Downloading trained YOLO model from MinIO: %s/%s", MODEL_BUCKET, model_key)
        try:
            minio_client.fget_object(MODEL_BUCKET, model_key, model_path)
        except Exception as e:
            logger.warning("Could not find best.pt in MinIO (%s), using default yolo11n.pt instead", e)
            model_path = "yolo11n.pt"

        # รัน YOLO Model Prediction
        model = YOLO(model_path)
        results = model(local_img_path)

        boxes_level1, boxes_level2, boxes_level3, boxes_level4 = 0, 0, 0, 0
        total_boxes = 0

        for r in results:
            boxes = r.boxes
            total_boxes = len(boxes)
            img_height = r.orig_shape[0]
            
            for box in boxes:
                xyxy = box.xyxy[0].tolist()
                y_center = (xyxy[1] + xyxy[3]) / 2.0
                
                # แบ่งระดับชั้นวางตามตำแหน่งแกน Y ของภาพ (สามารถปรับเปลี่ยนสัดส่วนได้ตามความเหมาะสมของมุมกล้อง)
                if y_center > img_height * 0.75:
                    boxes_level1 += 1
                elif y_center > img_height * 0.5:
                    boxes_level2 += 1
                elif y_center > img_height * 0.25:
                    boxes_level3 += 1
                else:
                    boxes_level4 += 1

        # คำนวณข้อมูลสถิติสต็อกเพิ่มเติมเพื่อลงฐานข้อมูล
        total_weight_kg = total_boxes * 10.0
        occupied_slots = total_boxes // 5
        empty_slots = max(0, 16 - occupied_slots)
        occupancy_pct = (occupied_slots / 16.0) * 100.0

        inventory_data = {
            "image_path": image_key,
            "split": "predict",
            "date": datetime.utcnow().date(),
            "time": datetime.utcnow().strftime("%H:%M"),
            "total_boxes": total_boxes,
            "total_weight_kg": total_weight_kg,
            "occupied_slots": occupied_slots,
            "empty_slots": empty_slots,
            "occupancy_pct": occupancy_pct,
            "boxes_level1": boxes_level1,
            "boxes_level2": boxes_level2,
            "boxes_level3": boxes_level3,
            "boxes_level4": boxes_level4,
            "inbound_boxes": 0,
            "outbound_boxes": 0,
            "cold_room_temp_c": -20.0,
            "humidity_pct": 80.0,
        }

        # บันทึกลงฐานข้อมูล PostgreSQL ผ่าน SessionLocal ของโปรเจค
        async with SessionLocal() as session:
            async with session.begin():
                await session.execute(insert(InventorySummary).values(**inventory_data))
            await session.commit()

        logger.info("Successfully processed and saved YOLO inference results for %s", image_key)
        return {
            "status": "success",
            "image_key": image_key,
            "total_boxes": total_boxes,
            "inventory_summary": inventory_data
        }