import io
from typing import Optional
from minio import Minio

from core.config import settings
from utils.logger import get_logger

logger = get_logger("storage_service")


class MinioStorageService:
    def __init__(self) -> None:
        self.client = Minio(
            endpoint=settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        self.default_bucket = settings.MINIO_BUCKET_NAME

    def ensure_bucket(self, bucket_name: Optional[str] = None) -> str:
        target_bucket = bucket_name or self.default_bucket
        try:
            if not self.client.bucket_exists(target_bucket):
                self.client.make_bucket(target_bucket)
                logger.info(f"Created bucket: {target_bucket}")
            return target_bucket
        except Exception as e:
            logger.error(f"Failed to ensure bucket {target_bucket}: {e}")
            raise e

    def upload_bytes(
        self,
        data: bytes,
        object_name: str,
        content_type: str = "application/octet-stream",
        bucket_name: Optional[str] = None,
    ) -> str:
        bucket = self.ensure_bucket(bucket_name)
        stream = io.BytesIO(data)
        self.client.put_object(
            bucket_name=bucket,
            object_name=object_name,
            data=stream,
            length=len(data),
            content_type=content_type,
        )
        logger.info(f"Uploaded object {object_name} to bucket {bucket}")
        return object_name

    def download_bytes(self, object_name: str, bucket_name: Optional[str] = None) -> bytes:
        bucket = bucket_name or self.default_bucket
        response = None
        try:
            response = self.client.get_object(bucket, object_name)
            return response.read()
        finally:
            if response:
                response.close()
                response.release_conn()

    def list_objects(self, prefix: str = "", bucket_name: Optional[str] = None) -> list[dict]:
        bucket = self.ensure_bucket(bucket_name)
        objects = self.client.list_objects(bucket, prefix=prefix, recursive=True)
        result = []
        for obj in objects:
            result.append(
                {
                    "object_name": obj.object_name,
                    "size": obj.size,
                    "last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
                }
            )
        return result

    def is_healthy(self) -> bool:
        try:
            self.client.list_buckets()
            return True
        except Exception as e:
            logger.warning(f"MinIO health check failed: {e}")
            return False


storage_service = MinioStorageService()
