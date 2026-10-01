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
- `training_worker/worker.py`: ARQ entry point สำหรับ training job
- `data_worker/worker.py`: กำหนด schedule/งานนำเข้าข้อมูลและเรียก ingestion modules
- `data_worker/ingestion/`: adapters สำหรับ financials, stocks, trades, database และ MinIO
- `Dockerfile`, `Dockerfile.data`: ภาพ worker สำหรับ inference/training และ data ingestion ตามลำดับ

ชื่อโมดูลในเอกสารรุ่นเก่าอาจไม่ตรงกับ layout ปัจจุบัน; source of truth สำหรับ entry point คือคำสั่ง `command` ของแต่ละ service ใน `compose.yml`/`compose.override.yml`

แม้ `data-worker` และ trade job จะทำงาน แต่ `trade_sources.yml` ปัจจุบันปิดทุก source ไว้ จึงข้ามการดึง trade data จนกว่าจะเปิดแหล่งข้อมูลที่ต้องการ

Forecast worker อ่าน time series จาก CSV ที่ระบุใน service; stock history ของ UI มาจาก PostgreSQL จึงเป็นคนละ data path ดูคำอธิบายและคำสั่งรันที่ [README หลัก](../README.md)
