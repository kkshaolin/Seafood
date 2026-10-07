# API modules

โมดูล HTTP ของ FastAPI ที่ `src/main.py` ลงทะเบียนใต้ prefix `/api`:

- `stock/`: อ่าน/นำเข้าข้อมูล stock
- `camera.py`: อ่าน frame, sampled frame และ camera log
- `sampling.py`: enqueue camera sampling และอ่าน sampling status/log
- `risk.py`: ประเมิน stock risk
- `settings.py`: อ่านและเขียน settings
- `huggingface_router.py`: สถานะและ sync model กับ Hugging Face Hub

Forecast routes แยกอยู่ที่ `src/forecasting/router.py`; endpoint ที่เปิดใช้จริงตรวจได้จาก `main.py`.
