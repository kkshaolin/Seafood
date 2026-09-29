# Database Migrations (Alembic)

โฟลเดอร์จัดการเวอร์ชันและโครงสร้างของฐานข้อมูล (Database Schema) 

การเปลี่ยนโครงสร้างตาราง (Models) จะต้องถูกสร้างเป็นไฟล์ Migration เสมอ เพื่อให้การอัปเดตหรือย้อนกลับ (Rollback) ข้อมูลใน PostgreSQL เป็นไปอย่างปลอดภัย

คำสั่งที่เกี่ยวข้อง:
- สร้าง Migration: `alembic revision --autogenerate -m "description"`
- อัปเดตฐานข้อมูล: `alembic upgrade head`
