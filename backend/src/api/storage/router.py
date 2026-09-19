from fastapi import APIRouter, File, HTTPException, UploadFile, status, Depends
from arq import create_pool
from arq.connections import RedisSettings

from core.config import settings
from services.storage import storage_service
from api.auth.service import get_current_user
from api.auth.model import User

router = APIRouter(prefix="/storage", tags=["storage"])


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_dataset_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Upload a file/dataset to MinIO object storage and enqueue a processing job."""
    try:
        contents = await file.read()
        object_name = f"user_{current_user.id}/{file.filename}"
        
        # 1. Upload to MinIO
        uploaded_key = storage_service.upload_bytes(
            data=contents,
            object_name=object_name,
            content_type=file.content_type or "application/octet-stream",
        )

        # 2. Enqueue background worker task via Redis
        job_id = None
        try:
            redis = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
            job = await redis.enqueue_job("minio_file_processor_task", uploaded_key)
            job_id = job.job_id if job else None
            await redis.aclose()
        except Exception:
            # Storage succeeded even if redis queue is unreachable
            pass

        return {
            "message": "File uploaded successfully",
            "object_name": uploaded_key,
            "size_bytes": len(contents),
            "job_id": job_id,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload file: {str(e)}",
        )


@router.get("/files")
async def list_user_files(
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """List all files uploaded by the current user."""
    prefix = f"user_{current_user.id}/"
    return storage_service.list_objects(prefix=prefix)
