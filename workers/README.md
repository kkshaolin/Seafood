# Workers Service (Background Task Processing)

โฟลเดอร์นี้สำหรับเก็บบริการ **Background Worker** ที่ประมวลผลงานหนักแบบ Asynchronous โดยใช้ **ARQ** ร่วมกับ **Redis Broker**

- แยกงานที่ใช้เวลาคำนวณสูง (Heavy Workload) หรือประมวลผล AI/ML ออกจาก HTTP Web Request
- รับงานจาก Backend API ผ่าน Redis Task Queue เพื่อประมวลผลตามลำดับคิว
- รองรับงานเช่น: การประมวลผลไฟล์ทั่วไป, การเทรนโมเดล AI, และการรัน Inference ตอบกลับผู้ใช้งาน

## สถาปัตยกรรม Worker แบบเฉพาะทาง (Specialized Workers)
ในโปรเจคนี้มีการแบ่งไฟล์ Worker ออกตามลักษณะงานและการรันคิวเพื่อไม่ให้งานบล็อกกัน:

1. **`worker.py`** (General Data Worker)
   - ใช้ประมวลผลข้อมูลทั่วไป เช่น `process_data_task` หรือ `minio_file_processor_task`
   - รันในคิวเริ่มต้น (`arq:queue`)
2. **`training_worker.py`** (Training Node)
   - ใช้สำหรับการเทรนโมเดลโดยเฉพาะ
   - มีฟังก์ชัน `train_model` ดึงข้อมูลจาก MinIO/HuggingFace เทรนบน GPU และส่งขึ้น MLflow
   - รับงานจากคิวแยกพิเศษ (`training_queue`) ป้องกันการรบกวนงานอื่น
3. **`inference_worker.py`** (Inference Node)
   - ใช้สำหรับการทำนายผลโดยดึงโมเดลมาจาก MLflow
   - มีฟังก์ชัน `inference_task` พร้อมระบบ In-memory `model_cache` เพื่อความรวดเร็ว
   - รับงานจากคิวแยกพิเศษ (`inference_queue`) 

## ขั้นตอนการเพิ่มงาน AI Task ใหม่
1. เขียนฟังก์ชัน `async def my_new_task(ctx, ...)` ในไฟล์ Worker ที่เหมาะสม
2. ลงทะเบียนฟังก์ชันใน `WorkerSettings.functions = [..., my_new_task]`
3. เรียกสั่งงานจาก Backend ด้วย `await redis.enqueue_job("my_new_task", arg1, _queue_name="your_target_queue")`
