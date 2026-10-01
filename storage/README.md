# Storage mounts

โฟลเดอร์นี้เป็นพื้นที่ runtime สำหรับไฟล์ข้อมูล/โมเดลที่ bind-mount หรืออ่านโดย workers ไม่ใช่ source code:

- `data/`: CSV input และ dataset ต่าง ๆ รวมถึง CSV ที่ forecasting worker ใช้
- `models/`: ไฟล์โมเดล time-series และ model artifacts ที่ worker สร้าง/โหลด
- `logs/`: log files หากตั้งค่าให้เขียนลง filesystem

ใน Git เก็บเพียง `.gitkeep` เพื่อรักษาโฟลเดอร์ว่างไว้ ข้อมูลจริง, model binaries และผลลัพธ์ generated ถูก ignore จึงไม่ปรากฏครบใน repository และไม่ควรเพิ่มไฟล์ข้อมูลอ่อนไหวหรือไฟล์ขนาดใหญ่โดยไม่จำเป็น
