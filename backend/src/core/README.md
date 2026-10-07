# Core configuration

`config.py` ประกาศ Pydantic Settings สำหรับ environment ของ FastAPI เช่น database, Redis, MinIO, Hugging Face, CORS และ Label Studio. ค่าใน environment สามารถทับค่า default; `settings` เป็น instance ที่ modules อื่น import ใช้.
