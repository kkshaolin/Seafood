"""ตั้งค่าทั้งหมดอ่านจาก environment variables (ค่า default เหมาะกับรันบนเครื่อง local)"""
import os
from dataclasses import dataclass
from pathlib import Path


def _csv(name: str, default: str) -> list[str]:
    return [x.strip() for x in os.getenv(name, default).split(",") if x.strip()]


@dataclass(frozen=True)
class Settings:
    database_url: str
    redis_url: str
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_secure: bool
    datasets_bucket: str
    stock_symbols: list[str]
    fx_symbols: list[str]
    price_backfill_years: int
    financials_cache_ttl: int
    trade_sources_file: str


def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv(
            "DATABASE_URL", "postgresql://admin:secretpassword@localhost:5433/my_database"
        ),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"),
        minio_endpoint=os.getenv("MINIO_ENDPOINT", "localhost:9000"),
        minio_access_key=os.getenv("MINIO_ACCESS_KEY", "admin"),
        minio_secret_key=os.getenv("MINIO_SECRET_KEY", "password123"),
        minio_secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
        # ตามแผน: MinIO /datasets/raw-trade/ และ /datasets/raw-financial/
        datasets_bucket=os.getenv("DATASETS_BUCKET", "datasets"),
        stock_symbols=_csv("STOCK_SYMBOLS", "TU,ASIAN,CFRESH,TC,SSF"),
        fx_symbols=_csv("FX_SYMBOLS", "USDTHB=X"),
        price_backfill_years=int(os.getenv("PRICE_BACKFILL_YEARS", "10")),
        financials_cache_ttl=int(os.getenv("FINANCIALS_CACHE_TTL", str(24 * 3600))),
        trade_sources_file=os.getenv(
            "TRADE_SOURCES_FILE", str(Path(__file__).with_name("trade_sources.yml"))
        ),
    )
