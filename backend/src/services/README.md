# Backend services

- `risk_service.py`: คำนวณ risk level แบบ deterministic จาก current stock, forecast, threshold และ preference
- `storage.py`: helper สำหรับตรวจสถานะและอ่าน/เขียน object ใน MinIO
- `hf_service.py`: ตรวจและ sync model กับ Hugging Face Hub และ MinIO

API routers เรียก service ตามความรับผิดชอบ; งาน inference และ training อยู่ใน worker packages.
