# Camera sampling worker

`worker.py` กำหนด ARQ queue `sampling_queue`, งาน on-demand และ daily cron ที่ปิดไว้โดยค่า default (`DAILY_SAMPLING_ENABLED=false`). `sampler.py` อ่าน frame จาก mock videos, crop, รัน YOLO, upload ภาพไป MinIO และบันทึก BoxLog/inventory data ตามการตั้งค่า.

`mock_videos/` มีสำเนาวิดีโอ mock; source ยังค้นหา assets ที่ `frontend/public/` และ candidate paths อื่นตามที่ระบุใน `sampler.py`. ต้องเตรียม model ที่ class มีคำว่า `box`; worker ไม่ fallback ไปใช้ COCO weights.
