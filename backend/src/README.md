# Backend source map

`src/main.py` เป็น entry point ของ FastAPI; นี่คือ router map ของ application ที่ลงทะเบียนอยู่ในปัจจุบัน:

- `api/stock/`: stock list, summary, products, history และ CSV upload
- `forecasting/router.py`: latest forecast, enqueue forecast/training และ job status
- `api/settings.py`: อ่านและอัปเดตการตั้งค่า
- `api/risk.py`: ประเมินความเสี่ยง
- `api/camera.py`: สตรีมภาพและข้อมูลกล้อง CCTV
- `api/sampling.py`: สุ่มตรวจภาพและควบคุมคิวสุ่มตรวจ
- `api/huggingface_router.py`: ซิงค์และตรวจสอบโมเดลกับ Hugging Face Hub

## Package responsibilities

- `core/`: application settings (config.py)
- `db/`: async SQLAlchemy engine, session factory และ FastAPI dependency
- `models/`: database models ที่สร้าง query/table
- `services/`: risk calculation, storage helper และ Hugging Face sync
- `utils/`: logging helpers

## ขอบเขตปัจจุบัน

Backend ลงทะเบียน routers ครบถ้วนสำหรับ stock, forecasting, camera, sampling, settings, risk และ huggingface ส่วนงานพยากรณ์ทางสถิติและคอมพิวเตอร์วิทัศน์ทำใน workers โดยแยกกระบวนการอย่างเป็นระบบ
