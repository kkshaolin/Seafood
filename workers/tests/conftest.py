"""
Unit tests รันได้เลย (ไม่ต้องมี infra)
Integration tests (Postgres/Redis) เปิดด้วย:
    TEST_DATABASE_URL=postgresql://admin:secretpassword@localhost:5433/my_database pytest workers/tests
ตารางถูกสร้างจาก SQLAlchemy models ของ backend จริง เพื่อให้ schema ตรงกับที่ worker upsert
"""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))                          # workers/ (ingestion, data_worker)
sys.path.insert(0, str(ROOT.parent / "backend" / "src"))  # backend models

TEST_DB = os.getenv("TEST_DATABASE_URL")
if TEST_DB:
    os.environ["DATABASE_URL"] = TEST_DB


class FakeStore:
    """แทน MinIO"""
    def __init__(self):
        self.objects, self.sha = {}, {}

    def put_bytes(self, key, data, content_type="", metadata=None):
        self.objects[key] = data
        self.sha[key] = (metadata or {}).get("sha256")
        return key

    def put_parquet(self, df, key):
        self.objects[key] = df.copy()
        return key

    def stored_sha256(self, key):
        return self.sha.get(key)


@pytest.fixture
def store():
    return FakeStore()


@pytest.fixture
def db_ready():
    if not TEST_DB:
        pytest.skip("set TEST_DATABASE_URL to run integration tests")
    from sqlalchemy import create_engine, text
    from ingestion import db as ingest_db
    from db.database import Base
    from models import market_data  # noqa: F401

    engine = create_engine(TEST_DB.replace("+asyncpg", ""))
    Base.metadata.drop_all(engine, tables=[t for n, t in Base.metadata.tables.items()
                                           if n in ("market_prices", "financial_statements", "ingestion_runs")])
    Base.metadata.create_all(engine)
    ingest_db.get_engine.cache_clear()
    ingest_db._table.cache_clear()
    yield engine
    engine.dispose()
