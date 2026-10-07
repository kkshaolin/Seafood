"""คอนฟิกแอปหลักที่อ่านค่า environment จาก .env และกำหนด URL, secret, MinIO, CORS
สำหรับ backend service ที่ถูก start ผ่าน compose.yml
"""

from pathlib import Path
from typing import Any
from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    # กำหนดตัวแปรและประเภทข้อมูล (Type Hinting)
    APP_NAME: str = "Eco App"
    APP_ENV: str = "development"
    SECRET_KEY: SecretStr = "change-me"
    DEBUG: bool = False  # สามารถใส่ Default Value ได้
    PORT: int = 8000    # Pydantic จะแปลงชนิดข้อมูลจาก String ใน .env เป็น Int ให้เอง

    # ค่าเชื่อมต่อ Database (PostgreSQL)
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5433/mydb"
    
    # ค่าเชื่อมต่อ Redis
    REDIS_URL: str = "redis://localhost:6379"
    
    # ค่าเชื่อมต่อ Label Studio
    LABEL_STUDIO_API_KEY: str = "YOUR_LABEL_STUDIO_API_KEY"
    LABEL_STUDIO_URL: str = "http://localhost:8080"

    # ค่าเชื่อมต่อ MinIO Object Storage
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "admin"
    MINIO_SECRET_KEY: str = "password123"
    MINIO_SECURE: bool = False
    MINIO_BUCKET_NAME: str = "ai-ecosystem-data"

    # ค่า Hugging Face Model Hub (Hybrid Cache-Aside)
    HF_REPO_ID: str = "kkshaolin/yolo_box"
    HF_TOKEN: str = ""

    # CORS Origins (สามารถระบุเป็น list, JSON string หรือ comma-separated string)
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
        "http://localhost:8081",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            v_str = v.strip()
            if v_str.startswith("[") and v_str.endswith("]"):
                import json
                try:
                    parsed = json.loads(v_str)
                    if isinstance(parsed, list):
                        return [str(i).strip() for i in parsed if str(i).strip()]
                except Exception:
                    pass
            return [i.strip() for i in v_str.split(",") if i.strip()]
        elif isinstance(v, list):
            return [str(i).strip() for i in v if str(i).strip()]
        return []

    jwt_secret_key: str = "change-me-secret-key-super-secure"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # ตั้งค่าคอนฟิกเพื่อเชื่อมโยงกับไฟล์ .env
    model_config = SettingsConfigDict(
        env_file=BASE_DIR.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

# เรียกใช้งาน
settings = Settings()

