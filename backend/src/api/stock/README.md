# Stock API

- `router.py` ประกาศ `/api/stock` endpoints สำหรับ upload, list, summary, products และ history
- `controller.py` ตรวจ CSV รูปแบบ monthly inventory และแปลงผล query เป็น response schemas
- `repository.py` รวม query/insert ที่ใช้กับ stock tables
- `schema.py` กำหนด request/response models ของ stock API
- `__init__.py` เป็น package marker

เส้นทางอ่านและเขียนข้อมูลหลักอยู่ใน PostgreSQL ผ่าน SQLAlchemy session dependency.
