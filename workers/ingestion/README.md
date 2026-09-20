# Data Ingestion (Data Sources & Ingestion Plan)

| กลุ่มข้อมูล | โค้ด | ความถี่ (cron ใน `data_worker.py`) | ปลายทาง |
|---|---|---|---|
| สถิติส่งออกกุ้ง/หมึกแช่แข็ง | `trade.py` (requests + BeautifulSoup) | จันทร์ 04:00 | MinIO `datasets/raw-trade/{source}/…` |
| ราคาหุ้นอาหารทะเล & ค่าเงิน | `stocks.py` (yfinance) | จ.–ศ. 17:30 | MinIO `datasets/raw-financial/prices/{symbol}/{YYYYMMDD}.parquet` + Postgres `market_prices` |
| งบการเงิน/กำไรขาดทุน | `financials.py` (yfinance) | อาทิตย์ 03:00 | Postgres `financial_statements` + Redis `seafood:financials:{symbol}` |

ทุกครั้งที่รันจะมีแถวใน `ingestion_runs` (status = success / partial / failed / skipped)

## รัน
```bash
docker compose up -d --build data-worker        # รอ backend healthy ก่อน (backend สร้างตาราง)

# สั่งรันทันทีผ่าน API (ต้อง login) — ครั้งแรกให้ backfill
POST /api/ingestion/prices      {"backfill": true}
POST /api/ingestion/financials  {}
POST /api/ingestion/trade       {"months_back": 120}
GET  /job_status/{job_id}       GET /api/ingestion/runs
```

## Config (env ของ `data-worker` ใน `compose.yml`)
`STOCK_SYMBOLS` (ใส่ TU ได้เลย ระบบต่อ `.BK` ให้), `FX_SYMBOLS` (default `USDTHB=X`),
`DATASETS_BUCKET` (default `datasets`), `PRICE_BACKFILL_YEARS` (default 10)

## สถิติส่งออก: ต้องใส่ URL จริงก่อน
แก้ `trade_sources.yml` แล้วตั้ง `enabled: true` — รองรับ 3 โหมด: `url_template`, `ckan`, `page_links`
(ตอนนี้ปิดทั้งหมด → job จะ `skipped`) ไฟล์ที่ไม่เปลี่ยนจะถูกข้ามด้วย sha256

## ข้อควรระวัง
- Yahoo ให้งบรายไตรมาสย้อนหลังแค่ ~4–5 ไตรมาส → ต้องรันสม่ำเสมอเพื่อสะสมใน DB
- symbol ที่ Yahoo ไม่มีข้อมูลจะถูกบันทึกใน `ingestion_runs.detail.problems` และรันต่อ (status = partial)
- Schema เป็นของ backend (`models/market_data.py` + Alembic `7c1d2e9a4b10`) — worker ไม่สร้างตารางเอง

## เทสต์
```bash
pip install pytest && pytest workers/tests                     # unit (ไม่ต้องมี infra)
TEST_DATABASE_URL=postgresql://admin:secretpassword@localhost:5433/my_database pytest workers/tests   # + integration
```
