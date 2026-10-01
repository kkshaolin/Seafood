# Backend source map

`src/main.py` เป็น entry point ของ FastAPI; นี่คือ router map ของ application ที่ลงทะเบียนอยู่ในปัจจุบัน:

- `api/stock/`: stock list, summary, products, history และ CSV upload
- `forecasting/router.py`: latest forecast, enqueue forecast/training และ job status
- `api/settings.py`: อ่านและอัปเดตการตั้งค่า
- `api/risk.py`: ประเมินความเสี่ยง
- `api/inventory.py`: inventory API ที่ลงทะเบียนแยกต่างหาก

## Package responsibilities

- `core/`: application settings/โค้ดฐานข้อมูลอีกชุดหนึ่ง; ตรวจสอบ imports ก่อนนำไปใช้ เพราะ app ใช้ `db/database.py` เป็น session provider
- `db/`: async SQLAlchemy engine, session factory และ FastAPI dependency
- `models/`: database models ที่สร้าง query/table
- `services/`: risk calculation และ MinIO storage helper
- `utils/`: logging helpers

## ขอบเขตปัจจุบัน

ไม่มี camera/auth router ใน `main.py` ปัจจุบัน แม้ frontend จะมี camera helpers; requests เหล่านั้นยังไม่รองรับจนกว่าจะลงทะเบียน backend route เพิ่ม ส่วนงานพยากรณ์ทางสถิติทำใน `workers/inference_worker/forecast_model/` ไม่ใช่ใน backend package นี้
