# Local backups

ไฟล์ในโฟลเดอร์นี้เป็น backup archives ที่สร้างไว้ใน workspace และไม่ถูกติดตามโดย Git:

- `postgres_backup_*.sql.gz`: PostgreSQL dump ที่ `scripts/backup_production.py` สร้างผ่าน `docker compose exec postgres pg_dump`
- `storage_models_*.tar.gz`: archive ของ `storage/models` ที่สร้างโดยสคริปต์เดียวกัน

สคริปต์เก็บจำนวนไฟล์ล่าสุดตาม `--keep-last` (ค่าเริ่มต้น 7 แยกตามชนิด backup). Archive อาจมีข้อมูลฐานข้อมูลหรือ model ภายใน จึงไม่ควรเปิดเผย อัปโหลด หรือ commit โดยไม่ผ่านการอนุมัติและตรวจสอบข้อมูลก่อน.
