# Sandbox และ prototype tests

ไฟล์ในโฟลเดอร์นี้เป็น scripts/tests ทดลอง ไม่ใช่ test suite หลักของ repository:

- `test_api_camera.py`, `test_api_stock.py`: ทดลองเรียก API ผ่าน FastAPI TestClient
- `test_arq.py`: ทดลองส่งงานเข้า Redis/ARQ
- `test_config.py`, `test_logging.py`: ทดลอง settings และ logging
- `test_forecasting.py`, `test_forecasting_unit.py`: prototype สำหรับ forecast/API/model
- `test_label_studio.py`: ทดลอง Label Studio client
- `test_postgres.py`, `test_stock.py`: สคริปต์ทดสอบฐานข้อมูลและข้อมูล stock
- `minio/`: ทดลอง MinIO versioning/lifecycle และมีไฟล์ภาพผลลัพธ์
- `workers_tests/`: tests ของ ingestion prototype

หลายไฟล์อ้างถึง model/package รุ่นก่อนที่ไม่มีใน tracked application source ปัจจุบัน (เช่น `ShrimpStockData`, `models.student` และ `forecasting.arimax`) จึงอาจรันไม่ได้โดยไม่ปรับโค้ด และบางสคริปต์แก้ไขข้อมูลหรือ configuration ของบริการจริง โปรดตรวจสอบก่อนเรียกใช้; ชุด tests หลักอยู่ใน `tests/`.
