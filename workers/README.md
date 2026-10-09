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
- `Dockerfile`: build image สำหรับ `forecasting-worker` และ `training-worker`; source ของ `data_worker/` ไม่ได้อยู่ใน checkout นี้ จึงไม่ถูกคัดลอก
Compose เปิด `forecasting-worker`, `sampling-worker` และ `training-worker`. `data-worker` ยังไม่เปิดใช้งานจนกว่าจะเพิ่ม source package `data_worker/` กลับมา

การฝึก ARIMA อัตโนมัติรายเดือนรองรับผ่าน ARQ cron แต่ปิดไว้โดยค่าเริ่มต้น:

- `MONTHLY_ARIMA_TRAINING_ENABLED=false` (ค่าเริ่มต้น) จะไม่ลงทะเบียน cron และไม่เริ่มฝึกเอง
- เมื่อตั้งเป็น `true` งานจะเริ่มวันที่ 1 เวลา 00:00 น. ตามเวลา `Asia/Bangkok` โดยใช้ ARIMA `auto_order`
- `MONTHLY_ARIMA_PRODUCT` เลือกสินค้าได้ โดยค่าเริ่มต้นคือ `Frozen_Seafood` (สินค้าที่หน้า Dashboard ใช้)
- เปิดใช้งานภายหลังได้โดยตั้ง `MONTHLY_ARIMA_TRAINING_ENABLED=true` ใน environment ของ Compose แล้วรัน `docker compose up -d --force-recreate training-worker` การฝึกแบบกดสั่งเองและ YOLO ไม่ได้รับผลกระทบ

ข้อกำหนดของ inventory CSV ที่ seed ต้องการและข้อกำหนด YOLO weights/dataset ระบุไว้ใน [README หลัก](../README.md).
