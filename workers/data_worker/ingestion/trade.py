"""สถิติการส่งออกกุ้ง/หมึกแช่แข็ง (Customs / MOC / data.go.th) -> MinIO raw-trade/

เก็บไฟล์ดิบตามที่ได้มาเท่านั้น (ยังไม่ parse) และเทียบ sha256 เพื่อข้ามไฟล์ที่ไม่เปลี่ยน
"""
import logging
import re
from datetime import date
from pathlib import PurePosixPath
from typing import Iterator, Optional
from urllib.parse import quote, unquote, urljoin, urlparse

import requests
import yaml
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import db
from .settings import get_settings
from .storage import RAW_TRADE_PREFIX, RawStore, sha256_hex

logger = logging.getLogger("ingestion.trade")

DATA_EXT = (".csv", ".xls", ".xlsx", ".zip")
TIMEOUT = (10, 120)


def make_session() -> requests.Session:
    """สร้าง HTTP session พร้อม User-Agent และ retry สำหรับข้อผิดพลาดชั่วคราว"""
    s = requests.Session()
    s.headers["User-Agent"] = "seafood-data-ingestion/1.0"
    retry = Retry(total=3, backoff_factor=1.5, status_forcelist=(429, 500, 502, 503, 504))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def load_sources(path: Optional[str] = None) -> list[dict]:
    """อ่านรายการแหล่งข้อมูลจาก YAML ที่กำหนด หรือไฟล์เริ่มต้นในแพ็กเกจ"""
    with open(path or get_settings().trade_sources_file, encoding="utf-8") as f:
        return (yaml.safe_load(f) or {}).get("sources", [])


def safe_filename(url: str) -> str:
    """ดึงชื่อไฟล์จาก URL และแทนอักขระที่ไม่ปลอดภัยสำหรับ object key"""
    name = PurePosixPath(unquote(urlparse(url).path)).name or "download"
    # ไม่ใช้ \w เพราะไม่ครอบคลุมสระ/วรรณยุกต์ไทย (จะทำให้ชื่อไฟล์เพี้ยน) — แทนเฉพาะอักขระที่ไม่ปลอดภัย
    return re.sub(r'[\\/:*?"<>|\s]+', "_", name)


def looks_like_html(data: bytes) -> bool:
    """ตรวจ prefix ของ response เพื่อแยกหน้า HTML ที่ส่งกลับมาแทนไฟล์"""
    head = data[:512].lstrip().lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html")


def _months_back(n: int, today: Optional[date] = None) -> Iterator[tuple[int, int]]:
    """เดือนล่าสุดที่ 'จบแล้ว' ย้อนไป n เดือน"""
    today = today or date.today()
    y, m = today.year, today.month
    for _ in range(n):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        yield y, m


def iter_files(src: dict, session: requests.Session, months_back: Optional[int] = None) -> Iterator[tuple[str, str]]:
    """สร้างคู่ relative key/URL โดยรองรับ URL template, CKAN และลิงก์จากหน้าเว็บ"""
    mode = src.get("mode")
    if mode == "url_template":
        for y, m in _months_back(months_back or src.get("months_back", 12)):
            url = src["url"].format(year=y, month=m)
            yield f"{y}-{m:02d}/{safe_filename(url)}", url
    elif mode == "ckan":
        r = session.get(
            f"{src['base_url'].rstrip('/')}/api/3/action/package_show",
            params={"id": src["dataset_id"]}, timeout=TIMEOUT,
        )
        r.raise_for_status()
        for res in r.json()["result"].get("resources", []):
            url = res.get("url") or ""
            fmt = (res.get("format") or "").lower()
            if url and (fmt in ("csv", "xls", "xlsx", "zip") or url.lower().endswith(DATA_EXT)):
                yield safe_filename(url), url
    elif mode == "page_links":
        r = session.get(src["page_url"], timeout=TIMEOUT)
        r.raise_for_status()
        rx = re.compile(src["link_regex"]) if src.get("link_regex") else None
        seen = set()
        for a in BeautifulSoup(r.text, "lxml").find_all("a", href=True):
            url = urljoin(src["page_url"], a["href"])
            if urlparse(url).path.lower().endswith(DATA_EXT) and url not in seen:
                if rx is None or rx.search(url) or rx.search(a.get_text(" ")):
                    seen.add(url)
                    yield safe_filename(url), url
    else:
        raise ValueError(f"unknown mode: {mode!r}")


def fetch_and_store(store: RawStore, session: requests.Session, name: str, rel: str, url: str,
                    force: bool = False) -> str:
    """ดาวน์โหลด ตรวจ response และ hash ก่อนจัดเก็บ; คืน uploaded, unchanged หรือ missing"""
    r = session.get(url, timeout=TIMEOUT)
    if r.status_code == 404:
        return "missing"
    r.raise_for_status()
    data = r.content
    if not data or (url.lower().endswith(DATA_EXT) and looks_like_html(data)):
        raise ValueError(f"expected a data file but got empty/HTML page: {url}")
    digest = sha256_hex(data)
    key = f"{RAW_TRADE_PREFIX}/{name}/{rel}"
    if not force and store.stored_sha256(key) == digest:
        return "unchanged"
    store.put_bytes(key, data, r.headers.get("Content-Type", "application/octet-stream"),
                    metadata={"sha256": digest, "source-url": quote(url, safe="/:?&=%")[:500]})
    return "uploaded"


def ingest_trade(source: Optional[str] = None, months_back: Optional[int] = None, force: bool = False,
                 store: Optional[RawStore] = None, session: Optional[requests.Session] = None,
                 sources: Optional[list[dict]] = None) -> dict:
    """เลือก source ที่เปิดใช้งาน ดึงไฟล์ บันทึกผลแต่ละไฟล์ และสรุปสถานะรอบงาน

    หากไม่มี source ที่เปิดไว้ จะปิดบันทึกรอบงานเป็น skipped โดยไม่เรียกแหล่งภายนอก
    """
    sources = sources if sources is not None else load_sources()
    sources = [s for s in sources if s.get("enabled") and (source is None or s["name"] == source)]
    run_id = db.start_run("trade", {"source": source, "months_back": months_back, "force": force})
    if not sources:
        detail = {"note": "no enabled sources — แก้ ingestion/trade_sources.yml (enabled: true)"}
        db.finish_run(run_id, "skipped", 0, None, detail)
        return {"run_id": run_id, "status": "skipped", **detail}

    store, session = store or RawStore(), session or make_session()
    counts = {"uploaded": 0, "unchanged": 0, "missing": 0}
    keys, problems = [], {}
    for src in sources:
        try:
            for rel, url in iter_files(src, session, months_back):
                try:
                    res = fetch_and_store(store, session, src["name"], rel, url, force)
                    counts[res] += 1
                    if res == "uploaded":
                        keys.append(f"{RAW_TRADE_PREFIX}/{src['name']}/{rel}")
                except Exception as e:  # noqa: BLE001 - พังไฟล์เดียวไม่ควรหยุดทั้ง source
                    problems[url] = f"{type(e).__name__}: {e}"
        except Exception as e:  # noqa: BLE001
            problems[src["name"]] = f"{type(e).__name__}: {e}"

    status = "success" if not problems else ("partial" if counts["uploaded"] + counts["unchanged"] else "failed")
    detail = {**counts, "problems": problems, "objects": keys}
    db.finish_run(run_id, status, counts["uploaded"], keys[-1] if keys else None, detail)
    return {"run_id": run_id, "status": status, **detail}
