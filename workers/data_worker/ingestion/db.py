"""PostgreSQL helper: upsert แบบ idempotent + บันทึกประวัติการรัน (ingestion_runs)

หมายเหตุ: ตารางถูกสร้างโดย backend (SQLAlchemy models / Alembic) ที่นี่ใช้ reflection
ดังนั้นถ้ายังไม่มีตารางจะ error ชัดเจนแทนที่จะสร้างซ้อนกับ Alembic
"""
import json
import logging
from datetime import date, datetime, timezone
from functools import lru_cache
from typing import Optional

import pandas as pd
from sqlalchemy import MetaData, Table, create_engine, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine

from .settings import get_settings

logger = logging.getLogger("ingestion.db")

PRICE_COLUMNS = [
    "symbol", "trade_date", "asset_type",
    "open", "high", "low", "close", "adj_close", "volume",
]
FIN_COLUMNS = ["symbol", "period_end", "statement", "line_item", "value"]


def _sync_url(url: str) -> str:
    """แปลง URL ที่ใช้ asyncpg ให้เป็น URL สำหรับ SQLAlchemy engine แบบ synchronous"""
    return url.replace("+asyncpg", "", 1)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """สร้างและ cache engine ฐานข้อมูล โดยตรวจการเชื่อมต่อของ connection ใน pool"""
    return create_engine(_sync_url(get_settings().database_url), pool_pre_ping=True)


@lru_cache(maxsize=None)
def _table(name: str) -> Table:
    """อ่าน metadata ของตารางที่ backend/Alembic สร้างไว้ แล้ว cache ตามชื่อตาราง"""
    return Table(name, MetaData(), autoload_with=get_engine())


def _records(df: pd.DataFrame, columns: list[str]) -> list[dict]:
    """เลือกเฉพาะคอลัมน์ปลายทางและแทนค่า missing ด้วย None ก่อนส่งให้ฐานข้อมูล"""
    out = df[columns].astype(object)
    out = out.where(pd.notna(out), None)
    return out.to_dict("records")


def _upsert(table_name: str, records: list[dict], pk: list[str], chunk: int = 2000) -> int:
    """เขียนข้อมูลเป็นชุดและอัปเดตแถวเดิมเมื่อชน primary key; คืนจำนวน input records"""
    if not records:
        return 0
    table = _table(table_name)
    with get_engine().begin() as conn:
        for i in range(0, len(records), chunk):
            stmt = pg_insert(table).values(records[i : i + chunk])
            update_cols = {
                c.name: stmt.excluded[c.name]
                for c in table.columns
                if c.name not in pk and c.name in records[0]
            }
            update_cols["ingested_at"] = func.now()
            conn.execute(stmt.on_conflict_do_update(index_elements=pk, set_=update_cols))
    return len(records)


def upsert_prices(df: pd.DataFrame) -> int:
    """ตัดราคาซ้ำตาม symbol/วัน แปลง volume เป็นจำนวนเต็ม nullable แล้ว upsert"""
    df = df.drop_duplicates(subset=["symbol", "trade_date"], keep="last").copy()
    df["volume"] = df["volume"].astype("Int64")
    return _upsert("market_prices", _records(df, PRICE_COLUMNS), ["symbol", "trade_date"])


def upsert_financials(df: pd.DataFrame) -> int:
    """ตัดงบซ้ำตาม symbol/งวด/งบ/รายการ แล้ว upsert เป็นชุดใหญ่"""
    pk = ["symbol", "period_end", "statement", "line_item"]
    df = df.drop_duplicates(subset=pk, keep="last")
    return _upsert("financial_statements", _records(df, FIN_COLUMNS), pk, chunk=5000)


def latest_trade_date(symbol: str) -> Optional[date]:
    """คืนวันราคาล่าสุดที่มีในฐานข้อมูลสำหรับใช้กำหนดจุดเริ่มดึงข้อมูล"""
    t = _table("market_prices")
    with get_engine().connect() as conn:
        return conn.execute(select(func.max(t.c.trade_date)).where(t.c.symbol == symbol)).scalar()


def load_financials(symbol: str) -> dict:
    """อ่านงบสะสมของ symbol แล้วจัดเป็น statement → งวด → รายการ → ค่า"""
    t = _table("financial_statements")
    q = select(t.c.statement, t.c.period_end, t.c.line_item, t.c.value).where(t.c.symbol == symbol)
    out: dict = {}
    with get_engine().connect() as conn:
        for stmt, period, item, value in conn.execute(q):
            out.setdefault(stmt, {}).setdefault(period.isoformat(), {})[item] = value
    return out


def start_run(dataset: str, params: Optional[dict] = None) -> int:
    """สร้างบันทึก ingestion_runs สถานะ running พร้อมพารามิเตอร์ และคืน id"""
    t = _table("ingestion_runs")
    with get_engine().begin() as conn:
        return conn.execute(
            t.insert()
            .values(dataset=dataset, status="running", detail=json.dumps({"params": params or {}}, default=str))
            .returning(t.c.id)
        ).scalar_one()


def finish_run(run_id: int, status: str, records: int = 0, object_key: Optional[str] = None,
               detail: Optional[dict] = None) -> None:
    """ปิดบันทึก ingestion_runs ด้วยสถานะ จำนวนแถว object key รายละเอียด และเวลาสิ้นสุด"""
    t = _table("ingestion_runs")
    with get_engine().begin() as conn:
        conn.execute(
            update(t).where(t.c.id == run_id).values(
                status=status,
                records_written=records,
                object_key=object_key,
                detail=json.dumps(detail or {}, default=str, ensure_ascii=False),
                finished_at=datetime.now(timezone.utc),
            )
        )
