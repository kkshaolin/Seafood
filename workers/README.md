# Workers Service (Background Task Processing)

โฟลเดอร์นี้สำหรับเก็บบริการ **Background Worker** ที่ประมวลผลงานหนักแบบ Asynchronous โดยใช้ **ARQ** ร่วมกับ **Redis Broker**

## สถาปัตยกรรม Worker แบบเฉพาะทาง (Specialized Workers)

1. **`worker.py`** (General Worker)
   - ใช้ประมวลผลข้อมูลทั่วไปและรันคิวเริ่มต้น
2. **`data_worker.py`** (Data Pipeline Worker)
   - ใช้รัน Task ที่เกี่ยวข้องกับการจัดการและเตรียมข้อมูล
3. **`forecasting_worker.py`** (Forecasting Worker)
   - ทำหน้าที่พยากรณ์ข้อมูล (Time-Series Forecasting) โดยทำงานคู่กับ Backend Forecasting Module
4. **`inference_worker.py`** (Inference Worker)
   - ทำนายผลจากโมเดล (ML/DL) ตอบกลับ API อย่างรวดเร็ว
5. **`training_worker.py`** (Training Worker)
   - สำหรับการเทรนโมเดลขนาดใหญ่และส่ง Metrics ไปยัง MLflow

## ระบบย่อย
- **`ingestion/`**
  - สคริปต์สำหรับดึงและรวบรวมข้อมูลภายนอก (Data Ingestion) เช่น ดึงข้อมูล Financials, Stocks, และ Trades 
  - ประกอบด้วยไฟล์เช่น `financials.py`, `stocks.py`, `trade.py`
- **`tests/`**
  - Unit Tests สำหรับ Worker และระบบ Ingestion
