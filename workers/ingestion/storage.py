"""MinIO helper สำหรับเก็บไฟล์ดิบ (raw landing zone)"""
import hashlib
import io
import logging
from typing import Optional

import pandas as pd
from minio import Minio
from minio.error import S3Error

from .settings import get_settings

logger = logging.getLogger("ingestion.storage")

RAW_TRADE_PREFIX = "raw-trade"
RAW_FINANCIAL_PREFIX = "raw-financial"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class RawStore:
    def __init__(self, client: Optional[Minio] = None, bucket: Optional[str] = None):
        s = get_settings()
        self.client = client or Minio(
            s.minio_endpoint,
            access_key=s.minio_access_key,
            secret_key=s.minio_secret_key,
            secure=s.minio_secure,
        )
        self.bucket = bucket or s.datasets_bucket
        self._bucket_ready = False

    def ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)
            logger.info("Created bucket %s", self.bucket)
        self._bucket_ready = True

    def put_bytes(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: Optional[dict] = None,
    ) -> str:
        self.ensure_bucket()
        self.client.put_object(
            self.bucket,
            key,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type,
            metadata=metadata,
        )
        return key

    def put_parquet(self, df: pd.DataFrame, key: str) -> str:
        buf = io.BytesIO()
        df.to_parquet(buf, index=False)
        return self.put_bytes(key, buf.getvalue(), "application/vnd.apache.parquet")

    def stored_sha256(self, key: str) -> Optional[str]:
        """sha256 ที่เราแนบไว้ตอนอัปโหลด (None ถ้าไม่มีไฟล์/ไม่มี metadata)"""
        self.ensure_bucket()
        try:
            stat = self.client.stat_object(self.bucket, key)
        except S3Error as e:
            if e.code in ("NoSuchKey", "NoSuchObject", "NotFound"):
                return None
            raise
        meta = {k.lower(): v for k, v in (stat.metadata or {}).items()}
        return meta.get("x-amz-meta-sha256")
