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
    return url.replace("+asyncpg", "", 1)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(_sync_url(get_settings().database_url), pool_pre_ping=True)


@lru_cache(maxsize=None)
def _table(name: str) -> Table:
    return Table(name, MetaData(), autoload_with=get_engine())


def _records(df: pd.DataFrame, columns: list[str]) -> list[dict]:
    out = df[columns].astype(object)
    out = out.where(pd.notna(out), None)
    return out.to_dict("records")


def _upsert(table_name: str, records: list[dict], pk: list[str], chunk: int = 2000) -> int:
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
    df = df.drop_duplicates(subset=["symbol", "trade_date"], keep="last").copy()
    df["volume"] = df["volume"].astype("Int64")
    return _upsert("market_prices", _records(df, PRICE_COLUMNS), ["symbol", "trade_date"])


def upsert_financials(df: pd.DataFrame) -> int:
    pk = ["symbol", "period_end", "statement", "line_item"]
    df = df.drop_duplicates(subset=pk, keep="last")
    return _upsert("financial_statements", _records(df, FIN_COLUMNS), pk, chunk=5000)


def latest_trade_date(symbol: str) -> Optional[date]:
    t = _table("market_prices")
    with get_engine().connect() as conn:
        return conn.execute(select(func.max(t.c.trade_date)).where(t.c.symbol == symbol)).scalar()


def load_financials(symbol: str) -> dict:
    """งบที่สะสมใน DB ทั้งหมดของ symbol -> {statement: {period_end: {line_item: value}}}"""
    t = _table("financial_statements")
    q = select(t.c.statement, t.c.period_end, t.c.line_item, t.c.value).where(t.c.symbol == symbol)
    out: dict = {}
    with get_engine().connect() as conn:
        for stmt, period, item, value in conn.execute(q):
            out.setdefault(stmt, {}).setdefault(period.isoformat(), {})[item] = value
    return out


def start_run(dataset: str, params: Optional[dict] = None) -> int:
    t = _table("ingestion_runs")
    with get_engine().begin() as conn:
        return conn.execute(
            t.insert()
            .values(dataset=dataset, status="running", detail=json.dumps({"params": params or {}}, default=str))
            .returning(t.c.id)
        ).scalar_one()


def finish_run(run_id: int, status: str, records: int = 0, object_key: Optional[str] = None,
               detail: Optional[dict] = None) -> None:
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
