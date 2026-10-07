# Backend API

บริการ FastAPI ที่เชื่อมต่อ PostgreSQL, Redis/ARQ และ MinIO รายละเอียดภาพรวมและวิธีรันทั้งระบบดูที่ [README หลัก](../README.md)

## Runtime

- `src/main.py` สร้าง FastAPI app, ตั้ง CORS/telemetry, ลงทะเบียน stock, forecasting, camera, sampling, settings, risk และ Hugging Face routers และให้ health endpoints (`/health`, `/health/live`, `/health/ready`)
- `src/db/database.py` จัดการ async SQLAlchemy engine/session ที่ API ใช้ ส่วน `src/models/` ประกาศตาราง
- Forecast requests ถูก enqueue ผ่าน Redis โดย router ใน `src/forecasting/router.py`; การคำนวณจริงอยู่ใน `workers/inference_worker/`
- Stock history อ่านจาก PostgreSQL; forecast service อ่าน `monthly_inventories` และ `box_logs` เป็นหลัก โดยมี CSV fallback เฉพาะกรณีที่ implementation รองรับ (ดู path และ schema ใน README หลัก)
- Camera API ให้ frame snapshot/inference, sampled frames และ logs จาก mock-video/model pipeline ไม่ใช่ live CCTV stream

Router ที่ลงทะเบียนจริงมีรายการข้างต้น; source ของ auth router ไม่ได้อยู่ใน `src/api/` ปัจจุบัน

## โฟลเดอร์

- `src/api/`: routes/controllers/schemas สำหรับ stock, camera, sampling, settings, risk และ Hugging Face
- `src/core/`: ค่าตั้งค่ากลาง (config.py); เส้นทาง DB หลักคือ `src/db/database.py`
- `src/db/`: engine และ session dependency
- `src/forecasting/`: request/response schemas และ API ที่ส่งงาน forecast/training ให้ ARQ
- `src/models/`: SQLAlchemy table definitions สำหรับ inventory, camera/box logs, settings และ forecast results
- `src/services/`: risk และ storage helpers
- `alembic/`: migration history; Compose ปัจจุบันไม่ได้สั่ง `alembic upgrade` โดยอัตโนมัติ

## Local checks

จาก `backend/` ติดตั้ง dependency ตาม `pyproject.toml`/`uv.lock` และรัน backend ตามคำสั่งใน README หลัก การรัน migration ต้องสั่ง Alembic แยกตาม environment ของฐานข้อมูล
