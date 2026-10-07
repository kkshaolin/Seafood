# Model trainers

- `arima_trainer.py`: ฝึก ARIMA จาก inventory data โดยอ่านฐานข้อมูลและมี CSV fallback ตาม implementation; จัดเก็บ model/metadata และ MLflow/MinIO integrations
- `yolo_trainer.py`: เตรียม dataset จาก MinIO แล้วฝึก YOLO ด้วย Ultralytics พร้อมบันทึก/upload artifacts
- `__init__.py`: package marker

Input formats, required files และ environment ดูใน implementation ของ trainer และ worker request schemas.
