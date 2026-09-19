# AI Ecosystem Workspace

รีโพสิทอรีนี้เป็นโครงสร้างระบบ **AI Engineering Ecosystem** แบบครบวงจร พัฒนาขึ้นสำหรับการทำงานจริงในระดับต่อยอดรองรับระบบ AI (เช่น Computer Vision, NLP Token Classification, LLM/RAG) โดยแบ่งสัดส่วนการทำงานอย่างเป็นโมดูล (Modular Architecture) แยกโหลดการทำงานระหว่าง Backend API, Training Node และ Inference Node อย่างชัดเจน ใช้งานง่าย ปลอดภัย และพร้อมสำหรับการขยายระบบ (Scale) ในอนาคต

## โครงสร้างโฟลเดอร์และไฟล์สำคัญ (Directory Structure)

```text
ai-ecosystem-workspace/
├── backend/                  # บริการ Backend API (FastAPI)
│   ├── alembic/              # Database Migration Management (Alembic)
│   ├── src/                  # Source Code หลัก
│   │   ├── api/              # API Controllers, Routers & Schemas
│   │   │   ├── auth/         # ระบบยืนยันตัวตน (Authentication & JWT Tokens)
│   │   │   ├── users/        # ระบบจัดการผู้ใช้งาน (User Management CRUD)
│   │   │   ├── storage/      # ระบบอัปโหลดและจัดการไฟล์ Dataset บน MinIO
│   │   │   └── predict/      # ระบบทำนายผล (Synchronous Inference API)
│   │   ├── core/             # ไฟล์ตั้งค่าส่วนกลาง (Configuration)
│   │   ├── db/               # การเชื่อมต่อฐานข้อมูล SQLAlchemy
│   │   ├── models/           # Data Models / Database Tables
│   │   ├── services/         # Helper Services & Business Logic
│   │   ├── utils/            # ฟังก์ชันช่วยเหลือ
│   │   └── main.py           # จุดเริ่มต้น FastAPI App, CORS, Health Check, และ Training Endpoints
│   ├── tests/                # Unit Tests & Integration Tests
│   ├── alembic.ini           # Alembic Configuration File
│   ├── pyproject.toml        # Python Dependencies (uv/pip)
│   └── Dockerfile            # Docker configuration สำหรับ Backend
│
├── storage/                  # โฟลเดอร์เก็บข้อมูลจำลองและระบบ (Volume Data)
│   ├── data/                 # ที่เก็บข้อมูล Dataset & Label Studio
│   ├── logs/                 # ไฟล์ Log การทำงานของระบบ
│   └── models/               # ที่เก็บไฟล์โมเดล AI (MinIO Artifacts)
│
├── workers/                  # บริการ Worker ทำงานเบื้องหลัง (Background Worker)
│   ├── worker.py             # ARQ Worker ประมวลผลข้อมูลทั่วไป (Data/File Processing)
│   ├── training_worker.py    # ARQ Worker สำหรับงานเทรนโมเดล (ใช้ GPU, ส่งผลขึ้น MLflow)
│   ├── inference_worker.py   # ARQ Worker สำหรับรันทำนายผล (โหลดจาก MLflow พร้อม Caching)
│   └── Dockerfile            # Docker configuration สำหรับ Worker ทั้งหมด
│
├── observability/            # การตั้งค่าระบบ Observability (Metrics, Logs, Traces)
│   ├── grafana/              # ตั้งค่า Datasource สำหรับ Grafana แบบอัตโนมัติ
│   ├── loki.yml              # ตั้งค่าระบบจัดเก็บ Log (Log Aggregation)
│   ├── otel-collector.yml    # ตั้งค่าตัวกลางรับ-ส่ง Traces และ Metrics (OpenTelemetry)
│   ├── prometheus.yml        # ตั้งค่าการเก็บ Time-series Metrics
│   ├── promtail.yml          # ตั้งค่า Agent ดึง Log จาก Docker ส่งให้ Loki
│   └── tempo.yml             # ตั้งค่าระบบจัดเก็บ Distributed Tracing
│
└── compose.yml               # การตั้งค่า Docker Compose สำหรับคอนเทนเนอร์ทั้งหมด รวมถึงเครื่องมือ Observability
```

## คุณสมบัติหลักที่อัปเดตล่าสุด (Key Technical Features)

1. **Decoupled Architecture**: แยกการทำงานระหว่าง Web Server (FastAPI), Training Worker, และ Inference Worker ขาดจากกัน รองรับการ Scale แบบอิสระ
2. **FastAPI & ARQ Integration**: 
   - Backend รับ API Request และส่งงานข้ามไปให้ Worker ผ่าน Redis Queue (`training_queue` และ `inference_queue`) 
   - รองรับ **Distributed Tracing Context Propagation** ข้าม Async Message Queue โดยการดึง Context ใส่ `carrier` แนบไปกับ Job Argument ทำให้ Trace ไม่ขาดตอน
   - มีระบบ Synchronous Inference (`/predict`) ที่ Backend รอรับผลจาก Worker กลับมาตอบผู้ใช้งานได้ทันที
3. **MLflow & MinIO Model Registry**: 
   - ระบบจัดการโมเดลอัตโนมัติ Training Worker เทรนเสร็จบันทึก Model Artifacts, Params, Metrics ลง MLflow (ซึ่งเก็บไฟล์ใน MinIO เบื้องหลัง)
   - Inference Worker โหลดโมเดลด้วย `mlflow.pyfunc.load_model` พร้อม In-memory Caching ช่วยลดเวลา Cold Start
4. **Database Migration ด้วย Alembic**: ควบคุมเวอร์ชันของตารางใน PostgreSQL ด้วย Migration Scripts
5. **CORS Security & Authentication**: ตั้งค่าอนุญาตให้ Frontend (เช่น React, Vue) เรียกใช้งาน API ได้ผ่าน `CORS_ORIGINS` พร้อมระบบ JWT Authentication 
6. **Full Observability Stack (O11y)**: ติดตั้งระบบตรวจสอบสถานะระบบครบวงจรด้วย **OpenTelemetry** ดักจับ Traces & Metrics จากโค้ดส่งไปที่ Collector ผูกรวมกับ Centralized Logs (Loki) และเก็บ Traces (Tempo)
   - **Log Correlation**: ใช้ Custom `TraceContextFilter` สอดแทรก `trace_id` และ `span_id` ลงใน Log อัตโนมัติ รองรับการเชื่อมต่อกับ Worker อย่างปลอดภัย
   - **Grafana Provisioning**: เชื่อม Datasource ไว้ล่วงหน้า สามารถคลิกจาก Log ข้ามไปดู Trace ได้ทันที (Log-to-Trace)
## ขั้นตอนการติดตั้งและการรันระบบ (Getting Started Guide)

### ข้อกำหนดเบื้องต้น (Prerequisites)
- **Docker & Docker Compose**: จำเป็นสำหรับการรัน Services ทั้งระบบอย่างสมบูรณ์แบบ
- **NVIDIA GPU & Drivers** (Optional): หากต้องการเทรนโมเดลด้วยความเร็วสูง (Docker Compose ต้องการ `nvidia` driver)
- **Python**: เวอร์ชัน 3.10 หรือ 3.11 (หากต้องการรันแบบ Local นอก Docker)

### 1. การตั้งค่า Environment Variables
สำหรับรันบน Docker ส่วนใหญ่ถูกเซ็ตอัปไว้ใน `compose.yml` แล้ว หากจะรัน Local หรือแก้ไข ให้ดูตัวแปรที่สำคัญดังนี้:
```env
DATABASE_URL=postgresql://admin:secretpassword@postgres:5432/my_database
REDIS_URL=redis://redis:6379
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=admin
MINIO_SECRET_KEY=password123
MLFLOW_TRACKING_URI=http://mlflow:5000
MLFLOW_S3_ENDPOINT_URL=http://minio:9000
AWS_ACCESS_KEY_ID=admin
AWS_SECRET_ACCESS_KEY=password123
```

### 2. การรันระบบแบบ End-to-End ด้วย Docker Compose
วิธีที่แนะนำที่สุดในการรันระบบทั้งหมด:
```bash
# รันระบบทั้งหมด (Backend, MLflow, MinIO, Redis, Postgres, Workers, Label Studio)
docker compose up -d

# ดูสถานะการทำงานของคอนเทนเนอร์ทั้งหมด
docker compose ps

# สเกล Inference Worker เพื่อรองรับโหลด API มหาศาล
docker compose up -d --scale inference-worker=3
```

### 3. การรันสำหรับนักพัฒนา (Local Development)
หากต้องการรันเซอร์วิสแบบไม่พึ่งพา Docker (รัน Services ฐานข้อมูลด้วย Docker แล้วรัน App ด้วย Python):
```bash
# รัน FastAPI (Backend)
cd backend
uv pip install -r pyproject.toml
uv run uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

# รัน Training Worker (Terminal 2)
cd workers
uv run arq training_worker.WorkerSettings

# รัน Inference Worker (Terminal 3)
uv run arq inference_worker.WorkerSettings
```

## รายการ API Endpoints ที่สำคัญ (Key API Endpoints)

### System Health
- `GET /health` : ตรวจสอบสถานะการเชื่อมต่อของระบบทั้งหมด (Postgres, Redis, MinIO)

### AI Pipelines (Core Features)
- `POST /add_train_queue_time` : สั่งเริ่มเทรนโมเดล (Asynchronous ส่งงานเข้า `training_queue` คืนค่า job_id ทันที)
- `GET /job_status/{job_id}` : ตรวจสอบสถานะการทำงานจาก ARQ (รองรับทั้งงานเทรนและทำนายผล)
- `POST /predict` : ส่งทำนายผล (Synchronous รอรับผลกลับมาพร้อมกับ Prediction JSON)

### Authentication & Users
- `POST /api/auth/register` : สมัครสมาชิกผู้ใช้งานใหม่
- `POST /api/auth/login` : เข้าสู่ระบบเพื่อรับ JWT Access Token
- `GET /api/auth/me` : ดูข้อมูลผู้ใช้ปัจจุบัน (ต้องส่ง Bearer Token)
- `GET /api/users` : เรียกดูรายชื่อผู้ใช้ทั้งหมดในระบบ

### Storage & Dataset Management
- `POST /api/storage/upload` : อัปโหลดไฟล์ Dataset เข้า MinIO
- `GET /api/storage/files` : ดึงรายการไฟล์ทั้งหมดใน MinIO ของผู้ใช้งานปัจจุบัน

---

## 📌 Notes & Port Assignments

- **FastAPI Backend**: `http://localhost:8000` (Swagger UI: `http://localhost:8000/docs`)
- **Grafana (Observability UI)**: `http://localhost:3000` (ไม่ต้องใช้รหัสผ่าน เข้าได้ทันที)
- **Prometheus (Metrics UI)**: `http://localhost:9090`
- **Label Studio**: `http://localhost:8080`
- **MinIO Web Console**: `http://localhost:9001` (Credentials: admin / password123)
- **MLflow UI**: `http://localhost:5000`
- **PostgreSQL**: `localhost:5433` (บน Host) / `5432` (ใน Network)
- **Redis**: `localhost:6379`
- **Loki & Tempo (APIs)**: `3100` และ `3200` (ใช้ภายใน Network สำหรับส่ง Logs และ Traces)
