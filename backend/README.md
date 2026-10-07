# Backend API

บริการ FastAPI ที่เชื่อมต่อ PostgreSQL, Redis/ARQ และ MinIO รายละเอียดภาพรวมและวิธีรันทั้งระบบดูที่ [README หลัก](../README.md)

## Runtime

- `src/main.py` สร้าง FastAPI app, ตั้ง CORS/telemetry, ลงทะเบียน stock, forecasting, camera, sampling, settings, risk และ huggingface routers และให้ `GET /health` (พร้อม `/health/live` และ `/health/ready`)
- `src/db/database.py` จัดการ async SQLAlchemy engine/session ที่ API ใช้ ส่วน `src/models/` ประกาศตาราง
- Forecast requests ถูก enqueue ผ่าน Redis โดย router ใน `src/forecasting/router.py`; การคำนวณจริงอยู่ใน `workers/inference_worker/`
- Stock history อ่านจาก PostgreSQL; forecasting worker ปัจจุบันอ่าน series จาก CSV ใน `storage/` (ดูหมายเหตุใน README หลัก)

โค้ด `api/` ที่ยังไม่มี directory เช่น camera/auth และโมดูลบางส่วนที่อยู่ในเอกสารเก่าไม่ใช่ router ที่ลงทะเบียนจาก `src/main.py` ในปัจจุบัน

## โฟลเดอร์

- `src/api/`: controllers/routes/schemas สำหรับ endpoints ที่ app ลงทะเบียน
- `src/core/`: ค่าตั้งค่ากลาง (config.py); เส้นทาง DB หลักคือ `src/db/database.py`
- `src/db/`: engine และ session dependency
- `src/forecasting/`: request/response schemas และ API ที่ส่งงาน forecast/training ให้ ARQ
- `src/models/`: SQLAlchemy table definitions สำหรับ stock, forecasts, settings และ market data
- `src/services/`: risk และ storage helpers
- `alembic/`: migration history; Compose ปัจจุบันไม่ได้สั่ง `alembic upgrade` โดยอัตโนมัติ

## Local checks

จาก `backend/` ติดตั้ง dependency ตาม `pyproject.toml`/`uv.lock` และรัน backend ตามคำสั่งใน README หลัก การรัน migration ต้องสั่ง Alembic แยกตาม environment ของฐานข้อมูล
