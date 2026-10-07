# คู่มือการเตรียมความพร้อมและการ Deploy สู่ Production (Production Deployment Guide)

เอกสารนี้ระบุรายละเอียด สถาปัตยกรรม ขั้นตอนการติดตั้ง การจัดการความปลอดภัย การสำรองข้อมูล และขั้นตอนการตรวจสอบความพร้อมสำหรับ **I_LoveSeafood AI Ecosystem** ในสภาพแวดล้อม Production

---

## 1. ภาพรวมสถาปัตยกรรมการ Deploy (Production Architecture)

ระบบประกอบด้วย Multi-container Stack ที่ถูกแยกการทำงานระหว่าง **โหมดพัฒนา (Development)** และ **โหมดใช้งานจริง (Production)** อย่างชัดเจน:

| องค์ประกอบ | โหมดพัฒนา (Development) | โหมดการผลิต (Production) |
|---|---|---|
| **Frontend** | Vite Dev Server (Hot Module Replacement) ผ่าน Node | Multi-stage Nginx Image ที่คอมไพล์ Static SPA (Dist) |
| **Backend** | Uvicorn พร้อม WatchFiles Reloading | Uvicorn Multi-workers (`--workers 4`) ประสิทธิภาพสูง ไม่เปิด Reload |
| **Workers** | ARQ รันผ่าน `watchfiles` Polling | ARQ รันเป็น Native Daemon โดยตรง ไม่เปิด File Watcher |
| **PostgreSQL** | พอร์ตโฮสต์ `5433:5432` สำหรับเครื่องมือ DB GUI | **ปิดพอร์ตโฮสต์** (`ports: []`) เข้าถึงได้เฉพาะในเครือข่าย Docker ภายใน |
| **Redis** | พอร์ตโฮสต์ `6379:6379` | **ปิดพอร์ตโฮสต์** (`ports: []`) เข้าถึงได้เฉพาะในเครือข่าย Docker ภายใน |
| **Backend, MinIO, MLflow, TensorBoard, Label Studio และ Observability** | เปิดพอร์ตสำหรับพัฒนา | **ปิดพอร์ตโฮสต์ทั้งหมด** ใช้ Docker network หรือช่องทางดูแลระบบที่เชื่อถือได้ |
| **Frontend** | HTTP พอร์ต `8081` | bind ที่ `127.0.0.1:8081` ให้ reverse proxy บนเครื่องเดียวกันส่งต่อผ่าน HTTPS |
| **Logging** | ไม่จำกัดขนาดล็อกอย่างเข้มงวด | จำกัดขนาด JSON log สูงสุด 20MB, เก็บไม่เกิน 5 ไฟล์หมุนเวียน |
| **CORS** | ยอมรับ Wildcard (`*`) และ Localhost | จำกัดเฉพาะ Domain/Origin ของ Production Frontend |

### แผนผังเครือข่ายและความปลอดภัย
- **External Network (เปิดให้ผู้ใช้ภายนอกเข้าถึงผ่าน Reverse Proxy / Firewall):**
  - Frontend SPA ผ่าน Reverse Proxy ที่เปิด HTTPS; frontend container bind เฉพาะ `127.0.0.1:8081`
  - Backend API และหน้าเครื่องมือดูแลระบบไม่ publish host ports; ใช้ Docker network หรือ VPN/SSH tunnel จากผู้ดูแล
- **Internal Network (`ai-network` ภายใน Docker Bridge):**
  - PostgreSQL (พอร์ต `5432`)
  - Redis (พอร์ต `6379`)
  - MinIO S3 API (พอร์ต `9000`)
  - OpenTelemetry Collector (พอร์ต `4317` / `4318`)
  - Loki (พอร์ต `3100`) & Tempo (พอร์ต `3200`)

---

## 2. การจัดการ Environment Variables และความลับ (Secrets Management)

ห้ามใช้ placeholder หรือรหัสผ่านเริ่มต้นในสภาพแวดล้อมจริง ให้สร้างไฟล์ `.env.production` จากแม่แบบ `.env.production.example` แล้วเปลี่ยนค่าตัวอย่างทั้งหมดก่อน deploy:

```bash
cp .env.production.example .env.production
```

### การสร้างรหัสผ่านและคีย์ที่มีความปลอดภัยสูง
สร้างสตริงสุ่มความยาว 32 bytes (64 hex characters) สำหรับแต่ละความลับ:
```bash
# บน Linux/macOS หรือ Git Bash / WSL:
openssl rand -hex 32

# หรือบน PowerShell:
-join ((65..90) + (97..122) + (48..57) | Get-Random -Count 32 | ForEach-Object {[char]$_})
```

### ตารางการตั้งค่า Environment Variables ที่สำคัญ

| ตัวแปร | ความจำเป็น | คำอธิบาย | ตัวอย่างค่า Production |
|---|---|---|---|
| `APP_ENV` | จำเป็น | สภาพแวดล้อมการทำงาน | `production` |
| `DEBUG` | จำเป็น | ปิด Debug mode ของ FastAPI | `false` |
| `POSTGRES_PASSWORD` | จำเป็น | รหัสผ่านผู้ดูแลฐานข้อมูล | *สร้างด้วย openssl rand* |
| `DATABASE_URL` | จำเป็น | URL การเชื่อมต่อฐานข้อมูลภายใน | `postgresql://admin:<STRONG_PASS>@postgres:5432/my_database` |
| `MINIO_ROOT_USER` | จำเป็น | ผู้ดูแลระบบ MinIO S3 และ access key ที่ backend/workers ใช้ | *กำหนดชื่อผู้ใช้เฉพาะ production* |
| `MINIO_ROOT_PASSWORD` | จำเป็น | รหัสผ่านผู้ดูแลระบบ MinIO | *สร้างด้วย openssl rand* |
| `SECRET_KEY` | จำเป็น | คีย์สำหรับเข้ารหัส Token / Session | *สร้างด้วย openssl rand* |
| `CORS_ORIGINS` | จำเป็น | รายการ Origin ที่อนุญาตให้เรียก API | `["https://app.yourdomain.com"]` |
| `GRAFANA_ADMIN_PASSWORD`| จำเป็น | รหัสผ่าน Admin สำหรับเข้า Grafana | *สร้างด้วยรหัสผ่านที่ซับซ้อน* |
| `GF_AUTH_ANONYMOUS_ENABLED`| จำเป็น | ปิดการเข้าถึง Grafana โดยไม่ล็อกอิน | `false` |
| `HF_TOKEN` | ทางเลือก | Hugging Face Access Token สำหรับ Model Hub | `hf_xxxxxxxxxxxxxxxx` |

---

## 3. ขั้นตอนการเตรียมฐานข้อมูลและการ Migrate (Database Migration & Seeding)

ระบบรองรับทั้ง **Alembic Database Migration** สำหรับ schema evolution และ **Data Ingestion Script** สำหรับข้อมูลตั้งต้น:

### 3.1 การรัน Database Migration (Alembic)
เมื่อระบบสตาร์ท Backend container แล้ว ให้รันคำสั่ง Migration ไปยัง Head ล่าสุด:
```bash
# ตรวจสอบ revision ปัจจุบัน
docker compose -f compose.yml -f compose.prod.yml exec backend alembic current

# รัน Migration สู่เวอร์ชันล่าสุด
docker compose -f compose.yml -f compose.prod.yml exec backend alembic upgrade head
```

### 3.2 การนำเข้าข้อมูลสถิติประวัติสต็อก (Initial Seed Data)
หากเป็นการติดตั้งระบบครั้งแรก ให้รันสคริปต์ประมวลผลข้อมูล 4 ตารางหลัก (`daily_inventories`, `monthly_inventories`, `yearly_inventories`, `box_logs`):
```bash
docker compose -f compose.yml -f compose.prod.yml exec backend python /workers/adjust_database_data.py
```

---

## 4. ขั้นตอนการสั่งเริ่มระบบ (Production Startup)

### 4.1 ตรวจสอบความถูกต้องของไฟล์ Compose
ก่อนเริ่มระบบ ให้ตรวจสอบว่า Configuration ของ production รวมกันอย่างสมบูรณ์:
```bash
docker compose -f compose.yml -f compose.prod.yml --env-file .env.production config --quiet
```
*หากคำสั่งไม่แสดง error แสดงว่าโครงสร้าง config ถูกต้องพร้อมใช้งาน*

Production Compose จะปฏิเสธการเริ่มระบบหากไม่ได้กำหนด MinIO user/password, Grafana admin password หรือ CORS origin และจะไม่ publish พอร์ต Backend, MinIO, databases หรือเครื่องมือดูแลระบบออกสู่ host. ตั้ง Reverse Proxy บน host ให้ส่ง HTTPS ไปยัง `127.0.0.1:8081`.

วิดีโอ `mockA.mp4`/`mockB.mp4` ยังคงใช้สำหรับการสาธิตได้ตามต้องการ ส่วน CSV สต็อกที่ bundle มากับ repository ถูกตัดแถวหลังวันที่ 7 ต.ค. 2026 (รายวัน) และหลังเดือน ต.ค. 2026 (รายเดือน); ให้ตรวจสอบ/นำเข้าข้อมูลธุรกิจจริงแยกต่างหากก่อนใช้คาดการณ์ใน production.

### 4.2 บิลด์และเริ่มการทำงานของ Container ทั้งหมด
```bash
docker compose -f compose.yml -f compose.prod.yml --env-file .env.production up -d --build
```

### 4.3 ตรวจสอบสถานะความพร้อมของ Container
```bash
docker compose -f compose.yml -f compose.prod.yml ps
```
คอนเทนเนอร์ทุกตัวต้องมีสถานะ `Up` หรือ `healthy`

---

## 5. การตรวจสอบความพร้อมด้วย Smoke Test (Automated Smoke Testing)

ระบบมีสคริปต์ตรวจ Frontend และ API ผ่าน Reverse Proxy 6 จุด; สามารถเพิ่ม private backend probes อีก 3 จุดเมื่อต่อผ่าน VPN/SSH tunnel:

```bash
# ตรวจ Frontend และ API ที่เปิดผ่าน HTTPS Reverse Proxy:
python scripts/smoke_test.py --frontend-url https://app.yourdomain.com

# เพิ่ม Backend health probes เมื่อเชื่อมต่อผ่าน private network หรือ SSH tunnel:
python scripts/smoke_test.py --frontend-url https://app.yourdomain.com --backend-url http://127.0.0.1:8000
```

ผล API checks ต้องผ่านทั้งหมด; private backend probes จะถูกรวมเมื่อระบุ `--backend-url`. MLflow, TensorBoard และระบบดูแลอื่น ๆ ไม่ถูกเปิด public จึงไม่ได้ทดสอบผ่าน public URL.

---

## 6. นโยบายการสำรองข้อมูลและการกู้คืน (Backup & Disaster Recovery)

### 6.1 การสำรองข้อมูลอัตโนมัติ
รันสคริปต์สำรองข้อมูลที่จะบันทึกทั้ง PostgreSQL dump แบบบีบอัด (`.sql.gz`) และน้ำหนักโมเดล AI (`.tar.gz`) พร้อมลบไฟล์เก่าที่เกินโควตา:
```bash
python scripts/backup_production.py --output-dir ./backups --keep-last 7
```

### 6.2 การตั้งค่า Cron Job สำหรับ Backup ประจำวัน (บน Linux Host)
```cron
# รันสำรองข้อมูลทุกวันเวลา 02:00 น.
0 2 * * * cd /path/to/I_LoveSeafood && python3 scripts/backup_production.py --keep-last 14 >> /var/log/backup_ecosystem.log 2>&1
```

### 6.3 ขั้นตอนการกู้คืนข้อมูลกรณีฉุกเฉิน (Disaster Recovery)

#### การกู้คืนฐานข้อมูล PostgreSQL:
```bash
gunzip -c ./backups/postgres_backup_<TIMESTAMP>.sql.gz | docker compose -f compose.yml -f compose.prod.yml exec -T postgres psql -U admin -d my_database
```

#### การกู้คืนน้ำหนักโมเดล AI (`storage/models`):
```bash
tar -xzf ./backups/storage_models_<TIMESTAMP>.tar.gz -C ./storage
```

---

## 7. กลยุทธ์การ Rollback (Rollback Strategy)

หากพบข้อผิดพลาดร้ายแรงหลังการ Deploy ให้ดำเนินการตามลำดับขั้นตอนนี้:

### ขั้นตอนที่ 1: สลับโค้ดหรือ Image กลับไปเวอร์ชันก่อนหน้า
```bash
# ดึง git tag เวอร์ชันที่มีเสถียรภาพล่าสุด
git checkout <PREVIOUS_STABLE_TAG>
```

### ขั้นตอนที่ 2: Rollback Database Migration (หากเวอร์ชันใหม่มีการแก้ schema)
```bash
docker compose -f compose.yml -f compose.prod.yml exec backend alembic downgrade -1
```

### ขั้นตอนที่ 3: สั่ง Rebuild และเริ่มระบบใหม่
```bash
docker compose -f compose.yml -f compose.prod.yml up -d --build
```

### ขั้นตอนที่ 4: รัน Smoke Test ซ้ำเพื่อยืนยันความเสถียร
```bash
python scripts/smoke_test.py
```

---

## 8. ข้อจำกัดที่ยังเหลือและคำแนะนำด้านความปลอดภัยขั้นสูง (Remaining Constraints & Recommendations)

1. **TLS / HTTPS Termination**:
   - ในปัจจุบัน Nginx ภายในคอนเทนเนอร์ให้บริการผ่านพอร์ต 80 แบบ Plain HTTP
   - **คำแนะนำ:** ติดตั้ง Reverse Proxy ชั้นนอกสุด (เช่น Nginx Reverse Proxy, Traefik, AWS ALB, หรือ Cloudflare) เพื่อจัดการใบรับรอง SSL/TLS (HTTPS)
2. **การป้องกันหน้า MLflow และ TensorBoard**:
   - ปัจจุบันพอร์ต `5000` และ `6006` ไม่มีการยืนยันตัวตนในตัว
   - **คำแนะนำ:** ปิดการเข้าถึงจากอินเทอร์เน็ตสาธารณะ ให้เข้าถึงได้เฉพาะผ่าน VPN หรือตั้งค่า HTTP Basic Authentication บน Nginx Reverse Proxy
3. **การจัดเก็บ Secrets ในระดับ Cloud**:
   - แนะนำให้ใช้เครื่องมือจัดการความลับเฉพาะทาง เช่น **AWS Secrets Manager**, **Google Secret Manager**, หรือ **HashiCorp Vault** แทนการบันทึกไว้ในไฟล์ `.env` บนเครื่องเซิร์ฟเวอร์
4. **Redis Authentication**:
   - คิวงาน Redis ปัจจุบันปิดพอร์ตภายนอกแล้ว แต่หากต้องขยายระบบเป็น Multi-node แนะนำให้เปิด `--requirepass` บน Redis Server

---
*จัดทำขึ้นเพื่อให้ระบบ ShrimpStock AI (I_LoveSeafood) มีความมั่นคง ปลอดภัย และพร้อมสำหรับการใช้งานจริงในระดับองค์กร*
