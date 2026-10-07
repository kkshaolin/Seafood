# Utility & Operations Scripts (I_LoveSeafood Ecosystem)

สคริปต์ในโฟลเดอร์นี้ใช้สำหรับการทดสอบ, บริหารจัดการโมเดล, สำรองข้อมูล และการปฏิบัติการระบบ:

### การทดสอบและการปฏิบัติการ Production
- **`smoke_test.py`**: ทดสอบความพร้อมการทำงานจริงของทุกบริการ (Backend Probes, Frontend SPA, MLflow, TensorBoard, APIs) แบบ End-to-End
- **`backup_production.py`**: สำรองข้อมูล PostgreSQL dump แบบบีบอัด (`.sql.gz`) และน้ำหนักโมเดล AI (`.tar.gz`) พร้อมระบบหมุนเวียนลบไฟล์สำรองเก่าอัตโนมัติ

### การจัดการชุดข้อมูลและโมเดล AI (MLOps)
- **`prepare_and_upload_yolo_dataset.py`**: จัดระเบียบชุดข้อมูลรูปภาพและ Labels จริง แบ่งสัดส่วน Train (70%), Val (15%), Test (15%) และอัปโหลดขึ้น MinIO bucket `datasets`
- **`evaluate_yolo_model.py`**: ทดสอบและประเมินประสิทธิภาพโมเดล YOLOv11 บน Held-out Test Set จริง โดยคำนวณ Precision, Recall, mAP@50 และ mAP@50-95
- **`sync_huggingface.py`**: ซิงค์โมเดลและ Metrics ระหว่าง MinIO S3 Storage และ Hugging Face Model Hub (`kkshaolin/yolo_box`)
- **`download_dataset.py`**: ดาวน์โหลด dataset จาก Hugging Face แล้วอัปโหลดไฟล์ไป MinIO
- **`export_openapi_to_csv.py`**: อ่าน OpenAPI schema จาก backend เพื่อส่งออก snapshot เป็น CSV/Excel
- **`generate_label_studio_token.py`**: สร้างและทดสอบ Token การเชื่อมต่อกับ Label Studio

> **ข้อควรระวัง:** ตรวจสอบ dependency, URL และ environment credentials ก่อนเรียกใช้แต่ละสคริปต์ และห้าม commit token หรือ credentials จริงลงใน repository
