# Camera sampling worker

`worker.py` กำหนด ARQ queue `sampling_queue` สำหรับงาน on-demand sampling ที่เรียกตอนกด Predict (cron ถูกปิดไว้). `sampler.py` อ่าน frame จาก mock videos ใน `frontend/public/` เท่านั้น (ณ จุดเวลาที่กด Predict), crop, รัน YOLO, upload ภาพไป MinIO และบันทึก BoxLog/inventory data.

วิดีโอ Mock ถูกอ่านจาก `frontend/public/` เท่านั้น (`mockA.mp4` สำหรับ Zone A และ `mockB.mp4` สำหรับ Zone B). ต้องเตรียม model ที่ class มีคำว่า `box`; worker ไม่ fallback ไปใช้ COCO weights.
