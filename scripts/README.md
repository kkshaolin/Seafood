# Utility scripts

สคริปต์ในโฟลเดอร์นี้เรียกใช้โดยผู้ดูแล/นักพัฒนาเป็นครั้งคราว และไม่ได้ถูกรันอัตโนมัติใน Compose:

- `download_dataset.py`: รับ dataset จาก Hugging Face แล้วอัปโหลดไฟล์ไป MinIO
- `export_openapi_to_csv.py`: อ่าน schema จาก backend ที่รันอยู่ (หรือสร้าง schema จาก FastAPI app) แล้วเขียน CSV/Excel snapshot
- `generate_label_studio_token.py`: ทดลอง login และอ่าน token จาก Label Studio ที่ต้องรันแยก; Compose ปัจจุบันไม่มี Label Studio service

ตรวจสอบ dependency, URL และ environment credentials ก่อนเรียกใช้แต่ละสคริปต์; อย่า commit token หรือ secret ที่ได้จากการรัน
