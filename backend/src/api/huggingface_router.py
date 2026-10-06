"""Router สำหรับ Hugging Face Model Hub (Hybrid Cache-Aside Pattern).

บริการ endpoints สำหรับ:
  - ตรวจสอบสถานะการเชื่อมต่อ Hugging Face, Local Cache, และ MinIO
  - Sync / Pull โมเดลล่าสุดจาก Hugging Face Hub สู่เครื่องและ MinIO
  - Publish / Push โมเดลที่เทรนใหม่ขึ้น Hugging Face Hub (kkshaolin/yolo_box)
"""

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from services.hf_service import hf_service
from utils.logger import get_logger

logger = get_logger("hf_router")

router = APIRouter(prefix="/hf", tags=["huggingface"])


class PullRequest(BaseModel):
    force: bool = False


@router.get("/status", summary="ตรวจสอบสถานะ Hugging Face Hub, Local Storage และ MinIO")
async def get_hf_status() -> Dict[str, Any]:
    """ส่งข้อมูลสถานะการเชื่อมต่อและรายการไฟล์โมเดลทั้งใน Local, MinIO และ Hugging Face"""
    try:
        return hf_service.get_status()
    except Exception as e:
        logger.error(f"Error fetching Hugging Face status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/push", summary="Publish / Push โมเดลขึ้น Hugging Face Model Hub")
async def push_models_to_hub() -> Dict[str, Any]:
    """อัปโหลดโมเดลที่มีในเครื่องขึ้น Hugging Face Model Hub (kkshaolin/yolo_box) พร้อม Model Card README"""
    try:
        return hf_service.push_models()
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error pushing models to Hugging Face: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pull", summary="Pull / Sync โมเดลจาก Hugging Face Model Hub")
async def pull_models_from_hub(req: PullRequest = PullRequest(force=False)) -> Dict[str, Any]:
    """ดาวน์โหลดโมเดลจาก Hugging Face Model Hub มาเก็บที่ Local Storage และ Seed เข้า MinIO"""
    try:
        return hf_service.pull_models(force=req.force)
    except Exception as e:
        logger.error(f"Error pulling models from Hugging Face: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/check-or-pull", summary="Hybrid Cache-Aside: ตรวจสอบและดึงโมเดลอัตโนมัติหากยังไม่มี")
async def check_or_pull_models() -> Dict[str, Any]:
    """ตรวจสอบว่าโมเดลครบหรือไม่ หากขาดจะดึงจาก Hugging Face Hub โดยอัตโนมัติ"""
    try:
        return hf_service.check_or_pull()
    except Exception as e:
        logger.error(f"Error in cache-aside check: {e}")
        raise HTTPException(status_code=500, detail=str(e))
