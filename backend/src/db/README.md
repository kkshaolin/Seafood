# Database access

`database.py` กำหนด SQLAlchemy async engine/session factory, FastAPI session dependency และ `create_database_schema()` ซึ่ง import stock models แล้วสร้างตารางจาก metadata. การสร้างตารางตอน startup เป็นคนละเส้นทางกับ Alembic migrations ใน `backend/alembic/`.
