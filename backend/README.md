# Backend Service (I_LoveSeafood)

บริการ Backend หลักของระบบ **I_LoveSeafood** พัฒนาด้วย **FastAPI** ทำหน้าที่เป็นศูนย์กลาง (Core API) ในการเชื่อมต่อระหว่างหน้าต่างผู้ใช้งาน (Frontend), ฐานข้อมูล (PostgreSQL), Object Storage (MinIO), และระบบจัดการคิวงาน (ARQ Workers)

## ระบบ Backend นี้ทำหน้าที่อะไรในโปรเจกต์?

Backend ของ I_LoveSeafood ไม่ได้เป็นแค่ระบบ CRUD ทั่วไป แต่ถูกออกแบบมาเพื่อรองรับงานด้าน Data และ AI Pipeline เฉพาะทางสำหรับข้อมูลอาหารทะเลและตลาด โดยมีหน้าที่หลักดังนี้:

1. **จัดการข้อมูลตลาดและสต็อกสินค้า (Market & Stock Management)**
   - รับและให้บริการข้อมูลสินค้า (Seafood Products), ปริมาณสต็อก, และข้อมูลตลาด/ราคาหุ้น (`api/stock`)
   - สั่งการ Ingestion Worker ให้ไปดึงข้อมูล Financials หรือ Trading Data จากแหล่งภายนอก (`api/ingestion`)

2. **พยากรณ์ความต้องการและราคาล่วงหน้า (Time-Series Forecasting)**
   - มีโมดูล `forecasting/` สำหรับสร้างโมเดลและพยากรณ์ข้อมูลแบบอนุกรมเวลา (Time-Series) โดยใช้ **ARIMAX** 
   - สามารถรับพารามิเตอร์ (p, d, q) เข้ามาทาง API เพื่อให้ Worker รันประมวลผล Forecasting กลับไปแสดงบน Dashboard

3. **รับภาพจากกล้องเพื่อวิเคราะห์ด้วย AI (Camera & Vision Pipeline)**
   - มี `api/camera` คอยรับภาพนิ่งหรือ Log จากกล้องที่หน้างาน (เช่น ภาพสายพานคัดแยกอาหารทะเล)
   - อัปโหลดภาพเข้าสู่ MinIO และสามารถเชื่อมโยงกับ Worker เบื้องหลังเพื่อรัน Inference ทำนายผลได้

4. **ประเมินความเสี่ยง (Risk Evaluation)**
   - มีบริการคำนวณและประเมินระดับความเสี่ยง (`services/risk_service.py`) เพื่อช่วยในการตัดสินใจทางธุรกิจ

5. **ระบบยืนยันตัวตนและการจัดการผู้ใช้ (Auth & Users)**
   - ควบคุมสิทธิ์การเข้าถึง API ทั้งหมดด้วย JWT Authentication

## โครงสร้างภายในโฟลเดอร์ `backend/`

- **`src/`**: แหล่งรวม Business Logic และโค้ดการทำงานทั้งหมด
  - **`api/`**: แบ่ง API Routes ตามหน้างานชัดเจน ได้แก่ `auth`, `camera`, `ingestion`, `predict`, `stock`, `storage`, `training`, `users`
  - **`forecasting/`**: โค้ดประมวลผลสถิติและ Machine Learning เฉพาะทางสำหรับ ARIMAX
  - **`models/`**: ตารางฐานข้อมูล SQLAlchemy (เช่น `market_data`, `stock`)
  - **`services/`**: ฟังก์ชันตัวช่วยและการคุยกับเซอร์วิสภายนอก (MinIO, Risk Calc)
  - **`core/` & `db/`**: การตั้งค่าตัวแปรระบบและการเชื่อมต่อ DB

- **`alembic/`**: ระบบควบคุมเวอร์ชันการสร้างและแก้ไขตารางฐานข้อมูล PostgreSQL
