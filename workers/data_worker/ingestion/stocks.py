"""ดึงและจัดเก็บราคาหุ้นอาหารทะเลกับค่าเงินจาก Yahoo Finance

ข้อมูลที่ได้จะถูกปรับเป็นตารางมาตรฐาน แล้วเขียนทั้งไฟล์ Parquet ใน MinIO
และแถวราคาแบบ idempotent ใน PostgreSQL; สัญลักษณ์ที่ผิดพลาดไม่หยุดตัวอื่น
"""
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import pandas as pd

from . import db
from .settings import get_settings
from .storage import RAW_FINANCIAL_PREFIX, RawStore

logger = logging.getLogger("ingestion.stocks")

OVERLAP_DAYS = 7  # ดึงย้อนทับของเดิมนิดหน่อย เผื่อ Yahoo ปรับราคา (split/dividend) แล้ว upsert ทับ


def normalize_symbol(symbol: str) -> str:
    """เติม .BK ให้หุ้น SET ที่ยังไม่มี suffix และคงรูปแบบ FX/ดัชนีไว้"""
    s = symbol.strip().upper()
    if "." in s or "=" in s or s.startswith("^"):
        return s
    return f"{s}.BK"


def asset_type(symbol: str) -> str:
    """จัดประเภท symbol เป็น fx สำหรับคู่เงิน Yahoo หรือ equity สำหรับหุ้น"""
    return "fx" if symbol.endswith("=X") else "equity"


def _fetch_history(symbol: str, start: date, end: Optional[date] = None) -> pd.DataFrame:
    """เรียกประวัติราคาจาก Yahoo ทีละ symbol เพื่อแยกผลกระทบเมื่อแหล่งข้อมูลผิดพลาด"""
    import yfinance as yf

    return yf.Ticker(symbol).history(start=start, end=end, auto_adjust=False, actions=False)


def to_frame(symbol: str, raw: pd.DataFrame) -> pd.DataFrame:
    """แปลงผล yfinance เป็นตารางมาตรฐาน หนึ่งแถวต่อ symbol ต่อวัน"""
    cols = ["symbol", "trade_date", "asset_type", "open", "high", "low", "close", "adj_close", "volume"]
    if raw is None or raw.empty:
        return pd.DataFrame(columns=cols)
    idx = pd.DatetimeIndex(raw.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)  # เก็บวันตามเวลาท้องถิ่นของตลาด
    out = pd.DataFrame(
        {
            "symbol": symbol,
            "trade_date": idx.normalize().date,
            "asset_type": asset_type(symbol),
            "open": raw["Open"].to_numpy(),
            "high": raw["High"].to_numpy(),
            "low": raw["Low"].to_numpy(),
            "close": raw["Close"].to_numpy(),
            "adj_close": (raw["Adj Close"] if "Adj Close" in raw else raw["Close"]).to_numpy(),
            "volume": raw["Volume"].to_numpy() if "Volume" in raw else 0,
        }
    )
    return out.dropna(subset=["close"]).reset_index(drop=True)


def ingest_prices(
    symbols: Optional[list[str]] = None,
    backfill: bool = False,
    start: Optional[date] = None,
    store: Optional[RawStore] = None,
) -> dict:
    """
    ดึงราคาแล้วเขียนไฟล์ดิบลง MinIO และข้อมูลตารางลง PostgreSQL

    ครั้งแรกหรือเมื่อเปิด backfill จะดึงย้อนหลังตาม PRICE_BACKFILL_YEARS;
    รอบปกติดึงต่อจากวันล่าสุดในฐานข้อมูลโดยย้อนทับ 7 วันเพื่อรับการปรับข้อมูล
    การ upsert ด้วย symbol และ trade_date ทำให้เรียกซ้ำได้โดยไม่เพิ่มแถวซ้ำ
    """
    cfg = get_settings()
    symbols = [normalize_symbol(s) for s in (symbols or cfg.stock_symbols + cfg.fx_symbols)]
    store = store or RawStore()
    today = date.today()
    run_id = db.start_run("prices", {"symbols": symbols, "backfill": backfill, "start": start})

    total, keys, problems = 0, [], {}
    for sym in symbols:
        try:
            if start:
                since = start
            elif backfill or (last := db.latest_trade_date(sym)) is None:
                since = today - timedelta(days=365 * cfg.price_backfill_years)
            else:
                since = last - timedelta(days=OVERLAP_DAYS)

            df = to_frame(sym, _fetch_history(sym, since))
            if df.empty:
                problems[sym] = "no data returned (symbol ผิดหรือ Yahoo ไม่มีข้อมูล?)"
                logger.warning("%s: no data since %s", sym, since)
                continue

            key = f"{RAW_FINANCIAL_PREFIX}/prices/{sym}/{today:%Y%m%d}.parquet"
            store.put_parquet(df, key)
            keys.append(key)
            total += db.upsert_prices(df)
            logger.info("%s: %d rows since %s", sym, len(df), since)
        except Exception as e:  # noqa: BLE001 - ให้ symbol อื่นทำงานต่อ
            logger.exception("%s failed", sym)
            problems[sym] = f"{type(e).__name__}: {e}"

    status = "success" if not problems else ("partial" if total else "failed")
    detail = {"symbols": symbols, "problems": problems, "objects": keys}
    db.finish_run(run_id, status, total, keys[-1] if keys else None, detail)
    return {"run_id": run_id, "status": status, "rows": total, **detail}
