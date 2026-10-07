# Backend source map

`src/main.py` เป็น entry point ของ FastAPI; นี่คือ router map ของ application ที่ลงทะเบียนอยู่ในปัจจุบัน:

- `api/stock/`: stock list, summary, products, history และ CSV upload
- `forecasting/router.py`: latest forecast, enqueue forecast/training และ job status
- `api/settings.py`: อ่านและอัปเดตการตั้งค่า
- `api/risk.py`: ประเมินความเสี่ยง
- `api/camera.py`: frame snapshots/inference, sampled frames และ camera logs จาก mock-video pipeline
- `api/sampling.py`: สุ่มตรวจภาพและควบคุมคิวสุ่มตรวจ
- `api/huggingface_router.py`: ซิงค์และตรวจสอบโมเดลกับ Hugging Face Hub

## Package responsibilities

- `core/`: application settings (config.py)
- `db/`: async SQLAlchemy engine, session factory และ FastAPI dependency
- `models/`: database models สำหรับ inventory, camera/box logs, settings และ forecast results
- `services/`: risk calculation, storage helper และ Hugging Face sync
- `utils/`: logging helpers

## ขอบเขตปัจจุบัน

Backend ลงทะเบียน routers สำหรับ stock, forecasting, camera, sampling, settings, risk และ Hugging Face; งานพยากรณ์และ sampling ที่ใช้ worker ถูก enqueue แยกจาก HTTP request
