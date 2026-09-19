# Helper Scripts

โฟลเดอร์นี้เก็บสคริปต์อัตโนมัติสำหรับช่วยเหลือการตั้งค่า การสร้าง Token การสแนปชอต API List และการจัดการสภาพแวดล้อมของโปรเจกต์

---

## 📂 รายการสคริปต์

### 1. `export_openapi_to_csv.py` (ระบบ Snapshot รายการ API เป็น Excel & CSV)
- ทำการสแนปชอต (Snapshot) รายการ API Endpoints ทั้งหมดของระบบจาก OpenAPI 3.0 Schema (`openapi.json`) แปลงเป็นไฟล์ **CSV** และ **Excel** เก็บที่ storage


### 2. `generate_label_studio_token.py`
- เชื่อมต่อกับ Label Studio API เพื่อดึงหรือสร้าง API User Token โดยอัตโนมัติ สำหรับนำไปใส่ใน `LABEL_STUDIO_API_KEY` ในไฟล์ `.env`
