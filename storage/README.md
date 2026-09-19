#  Storage (Persistent Data & Artifacts)

โฟลเดอร์นี้เก็บข้อมูลถาวรของระบบ AI Ecosystem เช่น ไฟล์ข้อมูล Dataset, ไฟล์ Log การทำงานของระบบ และไฟล์โมเดล AI (Model Checkpoints / Weights)

---

## โครงสร้างโฟลเดอร์ย่อย

```text
storage/
├── data/                 # ที่เก็บข้อมูลถาวรของ Label Studio และ local datasets
├── logs/                 # ที่เก็บไฟล์ Log ของแอปพลิเคชัน (สร้างโดย CustomLogger)
└── models/               # ที่เก็บไฟล์โมเดล AI ที่เทรนเสร็จแล้ว หรือไฟล์น้ำหนักโมเดล (Model Weights)
```


## 📌 
- `storage/data/` ถูกเชื่อมต่อ (Mount Volume) กับ Label Studio Docker Container ผ่าน `compose.yml`
- `storage/logs/` เป็นที่เก็บไฟล์ Log หมุนเวียนที่ดูแลโดย `utils/logger.py`
- ไฟล์ขนาดใหญ่ใน `storage/data/` หรือ `storage/models/` ควรได้รับการดูแลไม่ให้ commit ขึ้น Git Repository (อ้างอิงไฟล์ `.gitignore`)
