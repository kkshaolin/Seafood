# Database migrations

โฟลเดอร์นี้เก็บ revision history ที่ Alembic ใช้ปรับ schema ฐานข้อมูลตามลำดับ:

- `env.py`: โหลด metadata/models และ URL ฐานข้อมูลเพื่อรัน migration
- `versions/`: migration scripts ที่สร้าง/เปลี่ยนตาราง
- `script.py.mako`: template สำหรับ revision ใหม่
- `alembic.ini` อยู่ที่ `backend/alembic.ini` และกำหนดค่าเริ่มต้นของ Alembic

Compose ปัจจุบันไม่ได้รัน `alembic upgrade head` ตอนเริ่มบริการ; ให้ตรวจสอบ schema/environment และสั่ง migration อย่างชัดเจนก่อน deploy การสร้างตารางช่วงเริ่มระบบใน backend เป็นอีกกลไกหนึ่ง ไม่ได้แทน migration history
