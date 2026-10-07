# Alembic revisions

ไฟล์ในโฟลเดอร์นี้เป็น migration revisions ตาม `revision` และ `down_revision` ที่ระบุในแต่ละไฟล์:

- `548341a904e8_create_initial_tables.py`
- `7c1d2e9a4b10_add_market_data_tables.py`
- `a2e6a70fcc01_add_stock_management_models.py`
- `b3c47d9e8120_expand_forecast_model_version.py`

ตรวจ `upgrade()`/`downgrade()` ใน revision ก่อนนำไปใช้กับฐานข้อมูลจริง Compose ไม่ได้เรียก `alembic upgrade` โดยอัตโนมัติ และ backend มี schema bootstrap แยกต่างหาก.
