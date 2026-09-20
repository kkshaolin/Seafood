"""งบการเงินรายไตรมาส (yfinance) -> PostgreSQL (long format) + Redis cache

ข้อควรรู้: Yahoo ให้งบรายไตรมาสย้อนหลังแค่ ~4-5 ไตรมาสล่าสุด ดังนั้นต้องรันสม่ำเสมอ
(upsert สะสมลง DB ไปเรื่อย ๆ) ถ้าต้องการประวัติยาวกว่านั้นต้องใช้แหล่ง SET เพิ่ม
"""
import json
import logging
from typing import Optional

import pandas as pd

from . import db
from .settings import get_settings
from .stocks import normalize_symbol

logger = logging.getLogger("ingestion.financials")

# statement -> attribute ของ yfinance.Ticker (ลองตามลำดับ เผื่อชื่อเปลี่ยนตามเวอร์ชัน)
STATEMENT_ATTRS = {
    "income": ("quarterly_income_stmt", "quarterly_financials"),
    "balance": ("quarterly_balance_sheet",),
    "cashflow": ("quarterly_cashflow",),
}
CACHE_KEY = "seafood:financials:{symbol}"


def _fetch_statements(symbol: str) -> dict[str, pd.DataFrame]:
    """จุดที่ mock ในเทสต์"""
    import yfinance as yf

    ticker = yf.Ticker(symbol)
    out = {}
    for statement, attrs in STATEMENT_ATTRS.items():
        out[statement] = pd.DataFrame()
        for attr in attrs:
            try:
                df = getattr(ticker, attr)
            except Exception:  # noqa: BLE001
                continue
            if df is not None and not df.empty:
                out[statement] = df
                break
    return out


def to_long(symbol: str, statement: str, df: pd.DataFrame) -> pd.DataFrame:
    cols = ["symbol", "period_end", "statement", "line_item", "value"]
    if df is None or df.empty:
        return pd.DataFrame(columns=cols)
    rows = []  # ข้อมูลมีแค่หลักร้อยแถว: วน loop ตรง ๆ ชัดกว่าและเลี่ยงความต่างของ pandas.melt ระหว่างเวอร์ชัน
    for item, series in df.iterrows():
        for period, value in series.items():
            v = pd.to_numeric(value, errors="coerce")
            if pd.notna(v):
                rows.append((symbol, pd.Timestamp(period).date(), statement, str(item), float(v)))
    return pd.DataFrame(rows, columns=cols)


def _cache(symbol: str, payload: dict) -> bool:
    try:
        import redis

        cfg = get_settings()
        r = redis.Redis.from_url(cfg.redis_url, socket_connect_timeout=3)
        r.set(CACHE_KEY.format(symbol=symbol), json.dumps(payload), ex=cfg.financials_cache_ttl)
        return True
    except Exception as e:  # noqa: BLE001 - cache พังไม่ควรทำให้ ingestion ล้ม
        logger.warning("Redis cache failed for %s: %s", symbol, e)
        return False


def ingest_financials(symbols: Optional[list[str]] = None) -> dict:
    cfg = get_settings()
    symbols = [normalize_symbol(s) for s in (symbols or cfg.stock_symbols)]
    run_id = db.start_run("financials", {"symbols": symbols})

    total, problems, cached = 0, {}, []
    for sym in symbols:
        try:
            frames = [to_long(sym, st, df) for st, df in _fetch_statements(sym).items()]
            frames = [f for f in frames if not f.empty]
            if not frames:
                problems[sym] = "no financial statements returned"
                continue
            total += db.upsert_financials(pd.concat(frames, ignore_index=True))
            # cache จากข้อมูลสะสมใน DB (ไม่ใช่แค่ที่เพิ่งดึง) เพื่อให้ API อ่านจาก Redis ได้ครบ
            if _cache(sym, db.load_financials(sym)):
                cached.append(sym)
        except Exception as e:  # noqa: BLE001
            logger.exception("%s failed", sym)
            problems[sym] = f"{type(e).__name__}: {e}"

    status = "success" if not problems else ("partial" if total else "failed")
    detail = {"symbols": symbols, "problems": problems, "cached": cached}
    db.finish_run(run_id, status, total, None, detail)
    return {"run_id": run_id, "status": status, "rows": total, **detail}
