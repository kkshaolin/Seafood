# Backend Service (FastAPI)

โฟลเดอร์นี้เก็บบริการ **Backend API** ของระบบ AI Ecosystem พัฒนาด้วย **FastAPI** ร่วมกับ **Async SQLAlchemy 2.0**, **PostgreSQL**, **Alembic**, **JWT Authentication** และการเชื่อมต่อกับ **MinIO/MLflow**

- ให้บริการ RESTful API สำหรับระบบการลงทะเบียน เข้าสู่ระบบ และจัดการสิทธิ์ผู้ใช้งาน (Auth & Users)
- บริการ API อัปโหลดไฟล์ Dataset และข้อมูลสื่อเข้า MinIO Object Storage (`/api/storage`)
- บริการเชื่อมต่อเพื่อรันงาน AI เบื้องหลัง ทั้งงาน Train (`/add_train_queue_time`) และงาน Inference (`/predict`)
- คุยกับ Background Task Queue (Redis + ARQ Worker) ด้วยการแยกคิว (`training_queue`, `inference_queue`)
- ตรวจสอบสถานะความพร้อมของโครงสร้างระบบด้วยระบบ Health Check แบบครบวงจร (`/health`)

## โครงสร้างภายในโฟลเดอร์ Backend

```text
backend/
├── alembic/                  # ระบบจัดการ Database Schema Migration (Alembic)
│   ├── env.py                # ไฟล์ตั้งค่าการเชื่อมต่อ Async SQLAlchemy ของ Alembic
│   └── versions/             # ไฟล์ประวัติบันทึกการเปลี่ยนแปลงตารางใน PostgreSQL
│
├── src/                      # Source Code หลักของ Backend
│   ├── api/                  # Controllers, Routers และ Data Schemas
│   │   ├── auth/             # ระบบลงทะเบียน, Login (JWT)
│   │   ├── users/            # ระบบจัดการผู้ใช้งานแบบ CRUD
│   │   ├── storage/          # ระบบอัปโหลดไฟล์เข้า MinIO
│   │   └── predict/          # ระบบ Synchronous Inference API
│   │
│   ├── core/                 # ไฟล์ตั้งค่าและคอนฟิกระบบ
│   ├── db/                   # การเชื่อมต่อฐานข้อมูล (Async Engine)
│   ├── models/               # SQLAlchemy Database Models
│   ├── services/             # Business Logic & Service Helpers
│   ├── utils/                # ฟังก์ชันช่วยเหลือ (Logger)
│   └── main.py               # จุดเริ่มต้นแอป FastAPI, CORS Middleware และ Core Endpoints
│
├── tests/                    # Unit Tests & Integration Tests
├── alembic.ini               # ไฟล์ตั้งค่าคำสั่ง Alembic
├── pyproject.toml            # Python Dependencies & Project Metadata (uv)
└── Dockerfile                # Docker Image Build Configuration
```

---

## วิธีการรัน Backend

ก่อนรัน Server (หากไม่ได้ใช้ Docker Compose) ให้สั่งอัปเดตตารางฐานข้อมูลใน PostgreSQL:

```bash
# Alembic อัปเดตฐานข้อมูล
uv run alembic upgrade head
```

### 1. การรัน FastAPI Server
รัน Server ให้เรียกด้วย Python จาก `src/`:

```bash
uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. การเข้าใช้งาน API Documentation
เปิดใน Web Browser:
- **Interactive Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc Format**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 📌 หมายเหตุ
1. **การรันคำสั่ง**: ให้รันจากโฟลเดอร์ `backend/` เสมอ เพื่อให้การ Import Module ภายใน Python ทำงานได้ถูกต้อง
2. **สภาพแวดล้อม (.env)**: ระบบพึ่งพา Environment Variables จำนวนมาก (เช่น `REDIS_URL`, `MLFLOW_TRACKING_URI`) โปรดตรวจสอบให้แน่ใจว่าได้ระบุครบถ้วนก่อนรัน
