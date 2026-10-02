# I_LoveSeafood

โปรเจกต์นี้เป็นระบบตัวอย่างจัดการสต็อกกุ้งและข้อมูลตลาด ประกอบด้วย Dashboard, FastAPI, PostgreSQL, worker แบบ asynchronous และชุดเครื่องมือ observability โดยแยกส่วนที่ทำงานจริงใน Compose ออกจาก prototype/utility ที่ยังไม่เชื่อมต่อไว้ชัดเจน

## ภาพรวมการทำงาน

```text
Browser (React + Vite/Nginx)
  └─ /api/* ──> FastAPI backend
                 ├─ PostgreSQL: ประวัติ stock, settings, forecast results
                 ├─ Redis/ARQ ──> Forecast worker ──> forecast job
                 ├─ Redis/ARQ ──> Training worker ──> บันทึกโมเดล
                 └─ Risk API

Data worker ──> แหล่งข้อมูลตลาด/การเงิน ──> PostgreSQL และ MinIO
Application/containers ──> OpenTelemetry, Prometheus, Loki, Tempo ──> Grafana
```

## ส่วนที่ทำงานในระบบปัจจุบัน

- **Dashboard (`frontend/src/components/Dashboard.tsx`)** โหลดค่าตั้งค่า สรุปและประวัติ stock ผล forecast ล่าสุด และแสดงการประเมินความเสี่ยง การรัน forecast/training เริ่มงานผ่าน API แล้วติดตาม job
- **Backend (`backend/src/main.py`)** ลงทะเบียน API สำหรับ stock, forecasting, settings, risk และ inventory ตัว inventory ปัจจุบันเป็น mock/demo route พร้อม health check ที่ `/health`
- **Forecasting worker (`workers/inference_worker/worker.py`)** รับงานจาก `forecasting_queue`; **training worker (`workers/training_worker/worker.py`)** รับงานฝึกโมเดลจาก `training_queue`
- **Data worker (`workers/data_worker/worker.py`)** รันงาน ingestion ตามกำหนดเวลาและใช้โมดูลใน `workers/data_worker/ingestion/`; ตัวอย่างเช่น trade job จะข้ามการดึงข้อมูลเมื่อ source ถูกปิดไว้ใน config
- **PostgreSQL, Redis, MinIO และ observability services** ถูกกำหนดใน `compose.yml`

### แหล่งข้อมูล Forecast กับ Stock History ต่างกัน

Stock History ของหน้าเว็บอ่านจาก PostgreSQL ผ่าน `/api/stock/history` ส่วน `ForecastingService` ใน worker ปัจจุบันอ่าน time series จาก `storage/data/csv_file/shrimp_stock_monthly_4y.csv` ไม่ได้อ่านประวัติจากฐานข้อมูลโดยตรง และมี mapping `Premium_White_Shrimp` ไปเป็น `tiger_shrimp_size_L` สำหรับไฟล์ชุดนั้น ดังนั้นการมีประวัติ stock ในฐานข้อมูลอย่างเดียวไม่ได้รับประกันว่า worker จะสร้าง forecast ได้ ต้องมีไฟล์ CSV และข้อมูลสินค้าที่ตรงกับ mapping ด้วย

## ส่วนที่ยังไม่เชื่อมต่อหรือเป็นเครื่องมือเสริม

- กลุ่ม camera API ใน `frontend/src/api/camera.ts` และ `frontend/src/services/api.ts` เป็น client helpers แต่ backend ปัจจุบันยังไม่ได้ลงทะเบียน camera router; หน้า Dashboard จึงยังไม่มี stream กล้องจริง ส่วนภาพที่แสดงเป็น placeholder และ branch กล้องจริงยังไม่ทำงาน
- `frontend/src/services/api.ts` เป็น wrapper รุ่นเก่าที่ไม่ได้ใช้โดย Dashboard ปัจจุบัน ซึ่งใช้โมดูล `frontend/src/api/` แทน
- `frontend/src/api/stock.ts` ยังมี helper สำหรับเรียก endpoint upload แต่ปุ่มอัปโหลดถูกเอาออกจาก Dashboard แล้ว; backend upload endpoint ยังอยู่
- `backend/src/api/inventory.py` ลงทะเบียนกับ backend แต่หน้า Dashboard ปัจจุบันไม่ได้เรียกใช้งาน
- `scripts/` เป็นสคริปต์ที่เรียกใช้ด้วยตนเอง ไม่ได้เริ่มอัตโนมัติจาก Compose; แผนภาพใน `diagrams/` เป็นเอกสาร ไม่ใช่ input ของระบบ
- Worker ที่เริ่มทำงานไม่ได้แปลว่าทุก connector จะดึงข้อมูลจริงเสมอไป; ตรวจเปิด/ปิด source ใน config ของ ingestion ก่อนคาดหวังผลลัพธ์
- JSON เช่น lockfile และ Grafana dashboard definitions เป็นไฟล์ข้อมูลที่ parser ไม่รองรับ comment; คำอธิบายบทบาทอยู่ใน README และคอมเมนต์ของไฟล์ provisioning ที่อ้างถึงไฟล์เหล่านั้น

## โครงสร้างโฟลเดอร์

```text
.
├── backend/
│   ├── alembic/                 # migration scripts และการตั้งค่า Alembic
│   └── src/
│       ├── api/                 # endpoints: inventory, risk, settings, stock
│       ├── core/                # application configuration และ legacy/shared setup
│       ├── db/                  # SQLAlchemy async engine และ session dependency ที่ app ใช้
│       ├── forecasting/         # forecast API, request/response schemas
│       ├── models/              # ORM tables: stock, forecast, settings, market data
│       ├── services/            # risk และ object-storage helpers
│       └── main.py              # FastAPI entry point และ router registration
├── frontend/
│   ├── src/api/                 # API client แยกตามโดเมน
│   ├── src/components/          # Dashboard และ UI
│   ├── src/services/            # legacy API wrapper
│   └── Dockerfile, nginx.conf, vite.config.ts
├── workers/
│   ├── data_worker/             # ingestion schedule และ connectors
│   ├── inference_worker/        # ARIMA forecast และ worker entry point
│   └── training_worker/         # model training worker
├── observability/               # Collector, Prometheus, Loki, Tempo, Grafana config
├── scripts/                     # utilities ที่เรียกใช้ด้วยตนเอง
├── storage/                     # mount points สำหรับข้อมูลและโมเดล; เนื้อหาจริงถูก ignore
├── diagrams/                    # draw.io architecture/workflow source files
├── compose.yml                  # stack หลัก (production-style Nginx frontend)
└── compose.override.yml         # development overrides: Vite, hot reload, dashboards
```

โฟลเดอร์ dependencies, virtual environments, caches, build output, runtime data และ model binaries ไม่ใช่ source files ของโปรเจกต์ จึงไม่ได้รับ inline comments

## การเริ่มระบบด้วย Docker Compose (Quick Start)

### ข้อกำหนดเบื้องต้น (Prerequisites)
- ติดตั้ง [Docker Desktop](https://www.docker.com/products/docker-desktop/) (หรือ Docker Engine พร้อม Docker Compose v2)
- แนะนำให้จัดสรร RAM ให้ Docker อย่างน้อย 4 GB - 6 GB ขึ้นไป เพื่อรองรับการทำงานของ Database, ML Workers และ Observability Stack

### ขั้นตอนการเริ่มใช้งานครั้งแรก (First-Time Setup)

1. **Clone repository และเข้าไปยังโฟลเดอร์โปรเจกต์:**
   ```bash
   git clone <repository-url>
   cd I_LoveSeafood
   ```

2. **คัดลอกไฟล์ Environment Variables:**
   ```bash
   # บน Linux / macOS:
   cp .env.example .env

   # บน Windows (PowerShell):
   copy .env.example .env
   ```

3. **สั่งบิลด์และเริ่มระบบคอนเทนเนอร์:**
   ```bash
   # Compose จะรวม compose.override.yml อัตโนมัติ (เปิด Vite Dev Server, Hot-reload และ MinIO Buckets Init)
   docker compose up -d --build
   ```
   > [!NOTE]
   > ระบบจะทำงานตามลำดับโดยอัตโนมัติ:
   > 1. รอ PostgreSQL และ Redis พร้อมทำงาน
   > 2. สั่ง `minio-init` สร้าง Bucket ที่จำเป็นบน MinIO (`mlflow-artifacts`, `datasets`, `models`, `ai-ecosystem-data`) ให้อัตโนมัติ
   > 3. สั่ง `inventory-seed` เตรียมโครงสร้างตารางและโหลดชุดข้อมูล inventory ตัวอย่างลงฐานข้อมูล
   > 4. เริ่มต้น Backend API, Background Workers, MLflow, Observability Stack และ Frontend (Vite)

4. **ตรวจสอบสถานะคอนเทนเนอร์:**
   ```bash
   docker compose ps
   ```
   ทุกคอนเทนเนอร์ควรขึ้นสถานะ `Up` หรือ `Up (healthy)`

5. **ตรวจสอบ System Health ผ่าน API:**
   ```bash
   # ตรวจสอบว่า Database, Redis และ MinIO เชื่อมต่อสมบูรณ์
   curl http://localhost:8000/health
   ```
   ผลลัพธ์ที่ได้ควรแสดง `"status": "healthy"` และบริการทั้งหมดเป็น `"connected"`

---

### พอร์ตและหน้าจอของบริการในระบบ (Service URLs)

| บริการ (Service) | ที่อยู่จาก Host (URL) | ข้อมูลการเข้าใช้งาน (Credentials) |
|---|---|---|
| **Frontend Dashboard** | [http://localhost:8081/](http://localhost:8081/) | เข้าใช้งานได้ทันที (React + Vite dev server) |
| **Backend API & Swagger** | [http://localhost:8000/](http://localhost:8000/) / [Docs](http://localhost:8000/docs) | เอกสาร OpenAPI / Swagger UI |
| **MinIO Web Console** | [http://localhost:9001/](http://localhost:9001/) | User: `admin` / Password: `password123` |
| **MinIO S3 API Endpoint** | [http://localhost:9000/](http://localhost:9000/) | เข้าถึงผ่าน S3 API หรือ SDK |
| **MLflow Tracking UI** | [http://localhost:5000/](http://localhost:5000/) | ตรวจสอบ Experiment runs และ Artifacts |
| **Grafana Dashboards** | [http://localhost:3000/](http://localhost:3000/) | เข้าใช้งานแบบ Anonymous (ไม่ต้องล็อกอิน) |
| **Prometheus Metrics** | [http://localhost:9090/](http://localhost:9090/) | ดูสถานะ Metrics และ Target status |
| **Loki / Tempo** | `localhost:3100` / `localhost:3200` | Log & Distributed Trace Backends |
| **PostgreSQL** | `localhost:5433` (พอร์ต host) | User: `admin`, Password: `secretpassword`, DB: `my_database` |
| **Redis** | `localhost:6379` | Message broker สำหรับ ARQ Workers |

---

### คำสั่งจัดการระบบที่ใช้งานบ่อย (Useful Commands)

```bash
# ดู Log ของบริการหลักแบบเรียลไทม์
docker compose logs -f backend frontend forecasting-worker

# ดู Log เฉพาะ worker งานนำเข้าข้อมูล (Data Ingestion)
docker compose logs -f data-worker

# รีสตาร์ทเฉพาะบริการที่ต้องการหลังแก้ไขคอนฟิก
docker compose restart forecasting-worker data-worker

# หยุดการทำงานชั่วคราว (ไม่ลบข้อมูลและ Container)
docker compose stop

# ปิดระบบและลบคอนเทนเนอร์ (ข้อมูลใน Named Volumes ยังถูกเก็บรักษาไว้)
docker compose down

# ล้างระบบและคืนพื้นที่ทั้งหมดรวมถึงข้อมูลในฐานข้อมูล/MinIO (Clean Slate)
docker compose down -v
```

> [!TIP]
> **โหมด Production (Nginx Frontend):**
> หากต้องการรันระบบแบบ Production โดยไม่ใช้ Vite dev server ให้รันด้วยคำสั่ง:
> ```bash
> docker compose -f compose.yml up -d --build
> ```

## API ที่ใช้งานจาก Dashboard

ทุก endpoint ในตารางยกเว้น health check มี prefix `/api`:

| Endpoint | หน้าที่ |
|---|---|
| `GET /health` | ตรวจสถานะ database, Redis และ MinIO |
| `GET /stock/summary` | ภาพรวม stock |
| `GET /stock/history?product=...` | ประวัติ stock สำหรับกราฟ |
| `GET /forecast/latest?product=...` | forecast ล่าสุดที่บันทึกไว้ |
| `POST /forecast` | enqueue งาน forecast |
| `POST /forecast/train` | enqueue งานฝึกโมเดล |
| `GET /forecast/{job_id}` | ตรวจสถานะ/อ่านผลของงาน |
| `GET /settings`, `PUT /settings` | อ่าน/บันทึกค่าตั้งค่า |
| `POST /risk/evaluate` | ประเมินระดับความเสี่ยงจาก stock, forecast และ threshold |

มี endpoint stock เพิ่มเติม เช่น `/stock`, `/stock/products`, `/stock/upload` รวมถึง inventory routes แต่บาง endpoint ไม่มีปุ่ม/หน้าจอเรียกใช้ใน Dashboard ปัจจุบัน ดูรายการ routes ที่แน่นอนจาก Swagger UI

## การใส่คำอธิบายใน source

ไฟล์ source, scripts และ configuration ที่รองรับ comment มีคำอธิบายหน้าที่และส่วนสำคัญในรูปแบบที่ภาษานั้นรองรับแล้ว ไฟล์ machine-readable ที่ไม่รองรับ comment (เช่น JSON lockfile และ Grafana dashboard JSON) อธิบายไว้ในเอกสารแทน ไฟล์ dependencies, generated artifacts, local data, caches และ binaries ถูกยกเว้น
