# Backend `src`

โฟลเดอร์ `src` เป็นที่เก็บซอร์สโค้ดหลักของบริการ Backend (FastAPI) โดยแบ่งแยกสัดส่วนการทำงานชัดเจนตามหลัก Modular Architecture

## โครงสร้างและคำอธิบายโฟลเดอร์/ไฟล์หลัก

- **`api/`** — ชั้น API แบ่งตามโดเมน (Controllers/Routers/Schemas)
  - `auth/`: ระบบ Authentication
  - `camera/`: จัดการและวิเคราะห์ข้อมูลจากกล้อง (Computer Vision)
  - `ingestion/`: API สั่งงาน Data Ingestion
  - `predict/`: API สำหรับการทำนายผลทั่วไป
  - `stock/`: API สำหรับจัดการข้อมูลหุ้น
  - `storage/`: จัดการอัปโหลด/ดาวน์โหลดไฟล์บน MinIO
  - `training/`: จัดการ Job การเทรนโมเดล (ML)
  - `users/`: จัดการข้อมูลผู้ใช้งาน

- **`core/`** — การตั้งค่าระบบ
  - `config.py`: โหลดตัวแปรแวดล้อม
  - `database.py`: คอนฟิกฐานข้อมูล
  - `worker_settings.py`: ตั้งค่าการเชื่อมต่อ ARQ/Redis สำหรับ Worker

- **`db/`** — เลเยอร์ฐานข้อมูล
  - `database.py`: ระบบการเชื่อมต่อฐานข้อมูล

- **`forecasting/`** — ระบบพยากรณ์เวลาและข้อมูล (Time-Series Forecasting)
  - `arimax.py`: โมเดลพยากรณ์ ARIMAX
  - `metrics.py`: การคำนวณตัวชี้วัดความแม่นยำ
  - `preprocessing.py`: เตรียมข้อมูลก่อนเทรน
  - `router.py`, `schemas.py`, `service.py`

- **`models/`** — SQLAlchemy ORM Models
  - `market_data.py`: โครงสร้างตารางข้อมูลตลาด
  - `stock.py`: โครงสร้างตารางหุ้น
  - `student.py`: โครงสร้างตารางนักเรียน (ทดสอบ)

- **`services/`** — Business Logic layer
  - `risk_service.py`: บริการคำนวณความเสี่ยง
  - `storage.py`: บริการจัดการ MinIO Storage

- **`utils/`** — ฟังก์ชันช่วยเหลือ
  - `logger.py`: จัดการระบบ Logging 

- **`main.py`** — Entry Point ของ FastAPI App
