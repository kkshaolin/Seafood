# Worker ingestion tests

- `conftest.py` ตั้ง path สำหรับ imports และ fixtures ของ fake object storage/ฐานข้อมูล
- `test_ingestion.py` ทดสอบการ normalize stock symbols, แปลงราคา/financials/trade files, จัดการ incremental/idempotent ingestion และ partial failures

ส่วนฐานข้อมูลเปิดใช้เมื่อกำหนด `TEST_DATABASE_URL`; fixture จะ drop/recreate ตาราง ingestion ที่เลือกไว้ จึงควรใช้เฉพาะฐานข้อมูลทดสอบที่ทิ้งได้. Tests import `ingestion` modules ซึ่งไม่มีใน tracked worker source ปัจจุบัน ทำให้ชุดนี้ต้องมี source เพิ่มเติมก่อนจึงจะใช้งานได้จาก checkout นี้.
