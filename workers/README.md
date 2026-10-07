# Workers และงานข้อมูล

โฟลเดอร์นี้มี ARQ entry points และ helpers ที่ติดตามใน Git:

- `inference_worker/`: ประมวลผล forecast จาก `forecasting_queue`
- `sampling_worker/`: อ่านวิดีโอ mock, ตรวจจับ box, เก็บภาพใน MinIO และบันทึก inventory log
- `training_worker/`: dispatch งานฝึก ARIMA หรือ YOLO ที่รับจาก `training_queue`
- `inventory_data.py`: path resolver และ CSV loader ที่ใช้ร่วมกับ forecast/seed
- `seed_inventory.py`: ตรวจ schema แล้วนำ inventory CSV ตาม path ที่กำหนดเข้า `inventory_summaries`
- `adjust_database_data.py`: งานปรับ/นำเข้าข้อมูลฐานข้อมูลที่เรียกด้วยตนเอง
- `healthcheck.py`: health check ของ ARQ processes ตามชื่อ WorkerSettings
- `requirements.txt`, `requirements-data.txt`: dependency sets ของ worker images
- `Dockerfile`, `Dockerfile.data`: build images; Dockerfile.data ปัจจุบันอ้างถึง source package `data_worker/`

Compose ประกาศ `forecasting-worker`, `sampling-worker`, `training-worker` และ `data-worker`. อย่างไรก็ตาม `data_worker/` ไม่มีอยู่ใน tracked source ปัจจุบัน แม้ Compose และ `Dockerfile.data` จะอ้างถึงแพ็กเกจนี้ จึงอย่าถือว่า data-worker ทำงานได้จาก checkout นี้โดยไม่มี source เพิ่มเติม

ข้อกำหนดของ inventory CSV ที่ seed ต้องการและข้อกำหนด YOLO weights/dataset ระบุไว้ใน [README หลัก](../README.md).
