"""ตัวช่วยเขียนและตรวจสอบไฟล์ดิบใน MinIO ซึ่งทำหน้าที่เป็น raw landing zone

รองรับข้อมูล byte ทั่วไปและ DataFrame แบบ Parquet พร้อมตรวจ bucket และอ่าน
SHA-256 metadata เพื่อให้ ingestion ข้ามไฟล์ที่ไม่มีการเปลี่ยนแปลงได้
"""
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
    """คำนวณ SHA-256 ของเนื้อหาเพื่อใช้เปรียบเทียบไฟล์"""
    return hashlib.sha256(data).hexdigest()


class RawStore:
    """ห่อ MinIO client และจัดการ bucket/การอัปโหลดไฟล์ ingestion"""

    def __init__(self, client: Optional[Minio] = None, bucket: Optional[str] = None):
        """ใช้ client และ bucket ที่ส่งมา หรือสร้างจากค่าตั้งค่าปัจจุบัน"""
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
        """ตรวจและสร้าง bucket เพียงครั้งเดียวต่อ instance หากยังไม่มี"""
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
        """อัปโหลด bytes พร้อมชนิดเนื้อหาและ metadata แล้วคืน object key"""
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
        """serialize DataFrame เป็น Parquet ในหน่วยความจำ แล้วอัปโหลดเป็น object"""
        buf = io.BytesIO()
        df.to_parquet(buf, index=False)
        return self.put_bytes(key, buf.getvalue(), "application/vnd.apache.parquet")

    def stored_sha256(self, key: str) -> Optional[str]:
        """อ่าน SHA-256 ที่แนบไว้กับ object หรือคืน None เมื่อไม่มีไฟล์/metadata"""
        self.ensure_bucket()
        try:
            stat = self.client.stat_object(self.bucket, key)
        except S3Error as e:
            if e.code in ("NoSuchKey", "NoSuchObject", "NotFound"):
                return None
            raise
        meta = {k.lower(): v for k, v in (stat.metadata or {}).items()}
        return meta.get("x-amz-meta-sha256")
