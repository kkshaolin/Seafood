from pathlib import Path
from pydantic import SecretStr
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

    # CORS Origins (สามารถระบุเป็น list หรือ comma-separated string)
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
    ]

    jwt_secret_key: str = "change-me-secret-key-super-secure"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # ตั้งค่าคอนฟิกเพื่อเชื่อมโยงกับไฟล์ .env
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

# เรียกใช้งาน
settings = Settings()

