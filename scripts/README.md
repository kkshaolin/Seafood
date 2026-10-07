# Scripts

สคริปต์เหล่านี้เป็นเครื่องมือที่ผู้ดูแลเรียกใช้ตามความจำเป็น ไม่ใช่ชุดงานที่ backend เรียกโดยอัตโนมัติ:

| ไฟล์ | หน้าที่ตาม source |
|---|---|
| `backup_production.py` | เรียก `docker compose exec` เพื่อ dump PostgreSQL และ archive `storage/models`; มีตัวเลือกจำนวน backup ที่เก็บไว้ |
| `download_dataset.py` | ดาวน์โหลด dataset จาก Hugging Face Datasets แล้ว upload ไฟล์ไปยัง MinIO |
| `evaluate_yolo_model.py` | ตรวจ model และ held-out test images/labels ก่อนประเมิน; แจ้งว่ายังประเมินไม่ได้หากข้อมูลจริงไม่ครบ |
| `export_openapi_to_csv.py` | อ่าน OpenAPI จาก server หรือสร้างจาก FastAPI app แล้ว export CSV/Excel |
| `generate_label_studio_token.py` | ติดต่อ Label Studio เพื่อขอ auth/API token |
| `generate_word_report.py` | สร้างรายงาน Word |
| `import_inventory_csv.py` | สร้าง/ปรับตาราง inventory และ import CSV รายวัน/รายเดือน/รายปี |
| `prepare_and_upload_yolo_dataset.py` | จัด split จาก `images/` และ `labels/`, zip dataset และ upload ไป MinIO |
| `smoke_test.py` | ตรวจ frontend, API ที่ผ่าน frontend proxy และ backend probes เมื่อระบุ backend URL |
| `sync_from_supabase.py` | คัดลอกข้อมูลตารางจาก Supabase ไปยัง PostgreSQL ในเครื่อง |
| `sync_huggingface.py` | ตรวจและ sync model files ระหว่าง local storage, MinIO และ Hugging Face Hub |
| `upload_model.py` | สคริปต์ upload model ไป MinIO ที่ยังมี endpoint, credentials และ source path กำหนดตายตัวในไฟล์ |

ตรวจสอบ source, environment variables, dependency และปลายทางก่อนรันทุกครั้ง โดยเฉพาะ `import_inventory_csv.py` ซึ่ง truncate ตารางข้อมูลก่อน import และ `upload_model.py` ซึ่งมีค่าเชื่อมต่อ/พาธเฉพาะเครื่อง ไม่ควรใช้ตัวอย่าง credentials เหล่านั้นกับระบบจริง

ข้อกำหนดไฟล์ที่สคริปต์คาดหวังและคำเตือนเรื่องข้อมูลที่ไม่มีใน checkout นี้ดูได้ใน [README หลัก](../README.md).
