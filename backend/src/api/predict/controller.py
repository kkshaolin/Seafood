from fastapi import Request, HTTPException
import asyncio
from datetime import datetime
from api.predict.schema import InferenceRequest, InferenceResponse
from utils.logger import get_logger

from opentelemetry.propagate import inject

logger = get_logger("predict_controller")

async def predict(request_data: InferenceRequest, request: Request) -> InferenceResponse:
    job_id = f"infer_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # 1. validate request is done by Pydantic schema InferenceRequest
    
    redis_pool = request.app.state.redis_pool
    
    # ดึง Trace Context ปัจจุบันใส่ Carrier เพื่อส่งต่อให้ Worker (Context Propagation)
    carrier = {}
    inject(carrier)
    
    try:
        # ส่งงานเข้า Queue พร้อมแนบ Carrier และตั้ง TTL ป้องกันคิวตกค้าง
        job = await redis_pool.enqueue_job(
            'inference_task',
            request_data.model_uri,
            request_data.input_data,
            carrier,
            _job_id=job_id,
            _queue_name="inference_queue",
            _expires=60
        )
        
        if not job:
            raise HTTPException(status_code=500, detail="Failed to enqueue inference job")
            
        logger.info(f"Enqueued inference job {job_id}")
        
        # รอผลลัพธ์จาก Worker ภายในเวลา 30 วิ ป้องกัน Connection ฝั่ง API ค้าง
        result = await asyncio.wait_for(job.result(poll_delay=0.5), timeout=30.0)
        
        if result.get("status") == "error":
            logger.error(f"Inference job {job_id} error from worker: {result.get('error')}")
            raise HTTPException(status_code=500, detail=result.get("error"))
            
        return InferenceResponse(
            status=result.get("status", "success"),
            model_uri=result.get("model_uri", request_data.model_uri),
            predictions=result.get("predictions", []),
            job_id=job_id
        )
        
    except asyncio.TimeoutError:
        logger.error(f"Inference job {job_id} timed out waiting for worker. Aborting job.")
        try:
            # ยกเลิกงานใน Worker ทันทีหาก API หมดเวลารอ (ป้องกัน Worker รันงานฟรี)
            await job.abort()
        except Exception as abort_err:
            logger.error(f"Failed to abort job {job_id}: {abort_err}")
        raise HTTPException(status_code=504, detail="Inference process timed out")
    except Exception as e:
        logger.error(f"Inference job {job_id} failed: {str(e)}")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Inference process failed: {str(e)}")
