# Database Migrations (Alembic)

โฟลเดอร์นี้เก็บระบบควบคุมเวอร์ชันโครงสร้างฐานข้อมูล (Database Schema Migration) ของ PostgreSQL โดยใช้ **Alembic** ร่วมกับ **Async SQLAlchemy 2.0**

- บันทึกการเปลี่ยนแปลงโครงสร้างตาราง (Table Schema) ในรูปแบบไฟล์ Migration Script
- ป้องกันข้อมูลสูญหาย และสามารถย้อนกลับเวอร์ชัน (Rollback / Downgrade) ได้เมื่อเกิดปัญหา
- รองรับการปรับเปลี่ยนโครงสร้าง DB ในสภาพแวดล้อม Production

---

## โครงสร้างภายใน Alembic

```text
backend/alembic/
├── versions/         # ไฟล์สคริปต์ Migration บันทึกการเพิ่ม/ลดตารางหรือคอลัมน์
├── env.py            # สคริปต์ตั้งค่าการเชื่อมต่อ Async Engine และการตรวจจับ Auto-generate
└── script.py.mako    # แม่แบบ (Template) สำหรับสร้างสคริปต์ Migration ใหม่
```

---

## คำสั่งการใช้งานที่สำคัญ

### 1. สั่งสร้าง Migration Script ใหม่เมื่อมีการแก้ DB Model
เมื่อคุณทำการเพิ่มหรือแก้ไขไฟล์ Model ใน `backend/models/` หรือ `backend/api/*/model.py`:

```powershell
cd c:\Users\kitti\AIE\ecosystem\ai-ecosystem-workspace\backend
.\.venv\Scripts\alembic.exe revision --autogenerate -m "คำอธิบายการเปลี่ยนแปลง"
```

### 2. สั่งอัปเดตโครงสร้าง DB ให้เป็นเวอร์ชันล่าสุด (Upgrade)

```powershell
cd c:\Users\kitti\AIE\ecosystem\ai-ecosystem-workspace\backend
.\.venv\Scripts\alembic.exe upgrade head
```

### 3. สั่งย้อนกลับการอัปเดต 1 เวอร์ชัน (Downgrade)

```powershell
cd c:\Users\kitti\AIE\ecosystem\ai-ecosystem-workspace\backend
.\.venv\Scripts\alembic.exe downgrade -1
```
