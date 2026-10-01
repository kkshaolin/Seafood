# Data ingestion modules

โมดูลย่อยที่ `data_worker/worker.py` เรียกเพื่อดึงและจัดเก็บข้อมูลตลาดตาม schedule ที่กำหนดใน worker:

- `settings.py`: อ่าน environment และกำหนด symbols/bucket/options
- `stocks.py`: ดึงข้อมูลราคาหุ้นตาม symbols ที่กำหนด
- `financials.py`: ดึงข้อมูลด้านการเงิน
- `trade.py`: โหลดและประมวลผลข้อมูล trade ตาม source definitions
- `trade_sources.yml`: รายการแหล่ง/รูปแบบข้อมูล trade
- `db.py`: เขียนข้อมูล ingestion ลง PostgreSQL
- `storage.py`: ส่งไฟล์/dataset ไปยัง MinIO

โมดูลเหล่านี้ไม่ใช่ HTTP API; service `data-worker` ใน Compose เป็นตัวเริ่มวงจร ingestion และเชื่อม Redis, PostgreSQL และ MinIO
