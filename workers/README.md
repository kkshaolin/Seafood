# Background workers

Workers ใช้ ARQ/Redis เพื่อแยกงานจาก HTTP request; Compose ปัจจุบันเริ่ม worker 3 services:

| Compose service | ARQ settings | หน้าที่ |
|---|---|---|
| `forecasting-worker` | `inference_worker.worker.WorkerSettings` | รับ `forecasting_queue`, คำนวณ forecast และบันทึกผล |
| `training-worker` | `training_worker.worker.WorkerSettings` | รับ `training_queue` และฝึก/บันทึกโมเดล |
| `data-worker` | `data_worker.worker.WorkerSettings` | งาน ingestion และ schedule |

## Source layout

- `inference_worker/worker.py`: ARQ job entry point สำหรับ forecast
- `inference_worker/forecast_model/`: preprocessing, ARIMA fitting, metrics และ service ที่อ่าน CSV/บันทึกผล forecast

ข้อมูล inventory ใช้ไฟล์หลักที่ `storage/data/csvfile/inventory/inventory_summary.csv`
และรองรับไฟล์เดิม `storage/data/csv_file/inventory_summary (1).csv` เป็น fallback
เมื่อเริ่ม Compose จะมี `inventory-seed` สร้าง schema และนำเข้าข้อมูลลง `inventory_summaries`
ก่อนเริ่ม backend/workers; สั่งนำเข้าซ้ำได้ด้วย `docker compose run --rm inventory-seed`.
งาน ARIMA ฝึกจากข้อมูลเดียวกันและบันทึกโมเดลไว้ใน `storage/models/time_serie/`
พร้อมอัปโหลดสำเนาไปยัง MinIO; forecast อ่านข้อมูล inventory จาก PostgreSQL และใช้โมเดลที่เทรนไว้เมื่อพบ.
- `training_worker/worker.py`: ARQ entry point สำหรับ training job
- `data_worker/worker.py`: กำหนด schedule/งานนำเข้าข้อมูลและเรียก ingestion modules
- `data_worker/ingestion/`: adapters สำหรับ financials, stocks, trades, database และ MinIO
- `Dockerfile`, `Dockerfile.data`: ภาพ worker สำหรับ inference/training และ data ingestion ตามลำดับ

ชื่อโมดูลในเอกสารรุ่นเก่าอาจไม่ตรงกับ layout ปัจจุบัน; source of truth สำหรับ entry point คือคำสั่ง `command` ของแต่ละ service ใน `compose.yml`/`compose.override.yml`

แม้ `data-worker` และ trade job จะทำงาน แต่ `trade_sources.yml` ปัจจุบันปิดทุก source ไว้ จึงข้ามการดึง trade data จนกว่าจะเปิดแหล่งข้อมูลที่ต้องการ

Forecast worker อ่าน time series จาก CSV ที่ระบุใน service; stock history ของ UI มาจาก PostgreSQL จึงเป็นคนละ data path ดูคำอธิบายและคำสั่งรันที่ [README หลัก](../README.md)
