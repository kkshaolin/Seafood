from datetime import date

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import text

from ingestion import financials, stocks, trade
from ingestion import db as ingest_db


# ---------- unit: stocks ----------
def test_normalize_symbol():
    assert stocks.normalize_symbol("tu") == "TU.BK"
    assert stocks.normalize_symbol(" CFRESH ") == "CFRESH.BK"
    assert stocks.normalize_symbol("USDTHB=X") == "USDTHB=X"
    assert stocks.normalize_symbol("^SET.BK") == "^SET.BK"
    assert stocks.asset_type("USDTHB=X") == "fx" and stocks.asset_type("TU.BK") == "equity"


def _raw_prices(n=3, tz="Asia/Bangkok"):
    idx = pd.date_range("2026-09-14", periods=n, freq="D", tz=tz)
    return pd.DataFrame(
        {"Open": [10.0, 11, 12][:n], "High": [11.0, 12, 13][:n], "Low": [9.0, 10, 11][:n],
         "Close": [10.5, np.nan, 12.5][:n], "Adj Close": [10.4, np.nan, 12.4][:n],
         "Volume": [1000, 0, 3000][:n]}, index=idx)


def test_to_frame_drops_nan_close_and_keeps_local_date():
    df = stocks.to_frame("TU.BK", _raw_prices())
    assert list(df["trade_date"]) == [date(2026, 9, 14), date(2026, 9, 16)]
    assert (df["asset_type"] == "equity").all()


def test_to_frame_empty():
    assert stocks.to_frame("X.BK", pd.DataFrame()).empty


# ---------- unit: financials ----------
def test_to_long():
    wide = pd.DataFrame(
        {pd.Timestamp("2026-06-30"): [100.0, np.nan], pd.Timestamp("2026-03-31"): [90.0, 5.0]},
        index=["Total Revenue", "Net Income"])
    long = financials.to_long("TU.BK", "income", wide)
    assert len(long) == 3  # NaN ถูกตัด
    row = long[(long.line_item == "Net Income")].iloc[0]
    assert row.period_end == date(2026, 3, 31) and row.value == 5.0 and row.statement == "income"


# ---------- unit: trade ----------
def test_months_back_and_filename():
    assert list(trade._months_back(3, date(2026, 1, 15))) == [(2025, 12), (2025, 11), (2025, 10)]
    assert trade.safe_filename("https://x.go.th/a/สถิติ กุ้ง%202025.xlsx?dl=1") == "สถิติ_กุ้ง_2025.xlsx"
    assert trade.looks_like_html(b"  <!DOCTYPE html><html>") and not trade.looks_like_html(b"PK\x03\x04")


class FakeResp:
    def __init__(self, content=b"", status=200, text="", json_data=None, headers=None):
        self.content, self.status_code, self.text = content, status, text or content.decode("utf-8", "ignore")
        self._json, self.headers = json_data, headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._json


class FakeSession:
    def __init__(self, routes):
        self.routes = routes

    def get(self, url, **kw):
        return self.routes.get(url, FakeResp(status=404))


def test_iter_files_modes():
    html = '<a href="/f/shrimp_2025.xlsx">กุ้ง</a><a href="/f/other.csv">x</a><a href="/about">about</a>'
    s = FakeSession({"https://m.go.th/": FakeResp(text=html)})
    got = list(trade.iter_files({"mode": "page_links", "page_url": "https://m.go.th/", "link_regex": "shrimp"}, s))
    assert got == [("shrimp_2025.xlsx", "https://m.go.th/f/shrimp_2025.xlsx")]

    api = "https://data.go.th/api/3/action/package_show"
    s = FakeSession({api: FakeResp(json_data={"result": {"resources": [
        {"url": "https://d/x.csv", "format": "CSV"}, {"url": "https://d/page", "format": "HTML"}]}})})
    assert [u for _, u in trade.iter_files({"mode": "ckan", "base_url": "https://data.go.th", "dataset_id": "z"}, s)] == ["https://d/x.csv"]

    urls = list(trade.iter_files({"mode": "url_template", "url": "https://e/{year}{month:02d}.csv"}, s, months_back=2))
    assert len(urls) == 2 and urls[0][1].endswith(".csv")


def test_fetch_and_store_paths(store):
    data = b"a,b\n1,2\n"
    s = FakeSession({"https://e/a.csv": FakeResp(content=data, headers={"Content-Type": "text/csv"}),
                     "https://e/bad.csv": FakeResp(content=b"<html>blocked</html>")})
    assert trade.fetch_and_store(store, s, "src", "a.csv", "https://e/a.csv") == "uploaded"
    assert trade.fetch_and_store(store, s, "src", "a.csv", "https://e/a.csv") == "unchanged"
    assert trade.fetch_and_store(store, s, "src", "a.csv", "https://e/a.csv", force=True) == "uploaded"
    assert trade.fetch_and_store(store, s, "src", "n.csv", "https://e/none.csv") == "missing"
    with pytest.raises(ValueError):
        trade.fetch_and_store(store, s, "src", "bad.csv", "https://e/bad.csv")
    assert "raw-trade/src/a.csv" in store.objects


# ---------- integration (Postgres) ----------
@pytest.fixture
def fake_yahoo(monkeypatch):
    calls = []

    def fetch(symbol, start, end=None):
        calls.append((symbol, start))
        if symbol == "TC.BK":
            return pd.DataFrame()  # symbol ที่ Yahoo ไม่มี
        if symbol == "BOOM.BK":
            raise RuntimeError("yahoo down")
        return _raw_prices()

    monkeypatch.setattr(stocks, "_fetch_history", fetch)
    return calls


def test_ingest_prices_idempotent_and_incremental(db_ready, store, fake_yahoo):
    r1 = stocks.ingest_prices(["TU", "USDTHB=X"], store=store)
    assert r1["status"] == "success" and r1["rows"] == 4
    r2 = stocks.ingest_prices(["TU", "USDTHB=X"], store=store)  # รันซ้ำ ต้องไม่เพิ่มแถว
    with db_ready.connect() as c:
        assert c.execute(text("select count(*) from market_prices")).scalar() == 4
        assert c.execute(text("select asset_type from market_prices where symbol='USDTHB=X' limit 1")).scalar() == "fx"
        assert c.execute(text("select volume from market_prices where symbol='TU.BK' order by trade_date limit 1")).scalar() == 1000
    # รอบสอง incremental: เริ่มที่ วันล่าสุด(2026-09-16) - 7 วัน
    assert fake_yahoo[-1][1] == date(2026, 9, 9)
    assert any(k.startswith("raw-financial/prices/TU.BK/") for k in store.objects)


def test_ingest_prices_partial_failure(db_ready, store, fake_yahoo):
    r = stocks.ingest_prices(["TU", "TC", "BOOM"], store=store)
    assert r["status"] == "partial" and r["rows"] == 2
    assert set(r["problems"]) == {"TC.BK", "BOOM.BK"}
    with db_ready.connect() as c:
        st = c.execute(text("select status from ingestion_runs order by id desc limit 1")).scalar()
    assert st == "partial"


def test_ingest_financials_and_cache(db_ready, monkeypatch):
    wide = pd.DataFrame({pd.Timestamp("2026-06-30"): [100.0, 7.0]}, index=["Total Revenue", "Net Income"])
    monkeypatch.setattr(financials, "_fetch_statements",
                        lambda sym: {"income": wide, "balance": pd.DataFrame(), "cashflow": pd.DataFrame()})
    cached = {}
    monkeypatch.setattr(financials, "_cache", lambda sym, payload: cached.setdefault(sym, payload) is not None)
    r = financials.ingest_financials(["TU", "SSF"])
    assert r["status"] == "success" and r["rows"] == 4
    assert cached["TU.BK"]["income"]["2026-06-30"]["Net Income"] == 7.0
    financials.ingest_financials(["TU"])  # idempotent
    with db_ready.connect() as c:
        assert c.execute(text("select count(*) from financial_statements")).scalar() == 4


def test_ingest_trade_skips_when_nothing_enabled(db_ready, store):
    r = trade.ingest_trade(store=store, sources=[{"name": "x", "enabled": False}])
    assert r["status"] == "skipped"


def test_ingest_trade_end_to_end(db_ready, store):
    s = FakeSession({"https://e/202508.csv": FakeResp(content=b"a\n1\n"),
                     "https://e/202507.csv": FakeResp(content=b"a\n2\n")})
    src = [{"name": "cust", "enabled": True, "mode": "url_template", "url": "https://e/{year}{month:02d}.csv", "months_back": 3}]
    r = trade.ingest_trade(store=store, session=s, sources=src)
    assert r["status"] == "success" and r["missing"] >= 1 and r["uploaded"] + r["unchanged"] + r["missing"] == 3
