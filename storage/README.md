# Storage (Local Data & Mounts)

โฟลเดอร์ที่ใช้สำหรับ Mount Volume ของ Services ต่าง ๆ เพื่อให้ข้อมูลยังคงอยู่ (Persistent Data) 

## โครงสร้างหลัก
- **`data/`**: เก็บข้อมูลดิบ, ข้อมูลเทรน (เช่น `conll2003`), ข้อมูลรูปภาพจาก MinIO, ข้อมูล Label Studio, และการส่งออกข้อมูล CSV/Excel (`api_snapshot.csv`)
- **`logs/`**: เก็บไฟล์บันทึกการทำงานของระบบ (Application Logs, Worker Logs, Training Logs)
- **`models/`**: เก็บไฟล์โมเดลที่ถูกเทรนและบันทึกเอาไว้ แบ่งออกเป็นโมเดลสำหรับ Time-Series และ Non-Time-Series รวมถึงโมเดลที่มี Checkpoint ระหว่างเทรน
