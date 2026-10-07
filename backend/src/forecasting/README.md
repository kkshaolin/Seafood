# Forecast API

- `router.py` enqueue forecast และ ARIMA/YOLO training jobs ลง Redis/ARQ, อ่าน job status และ query forecast ล่าสุด
- `schemas.py` กำหนด payload/response models สำหรับ forecast, job status และ YOLO training
- `__init__.py` เป็น package marker

การประมวลผล forecast ทำใน `workers/inference_worker/forecast_model/`; การฝึกโมเดลทำใน `workers/training_worker/trainers/`.
