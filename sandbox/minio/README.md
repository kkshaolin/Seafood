# MinIO sandbox

`minio_test.py` เป็นสคริปต์ทดลอง bucket `my-profile`: สร้าง bucket เมื่อไม่มี, เปิด versioning, ตั้ง lifecycle สำหรับ noncurrent versions, และมี helper สำหรับ upload/download/list versions.

หากรันตาม `__main__` สคริปต์จะเปลี่ยน configuration ของ bucket และพยายาม upload `sandbox/myphoto_v2.jpg`; ไฟล์ต้นทางดังกล่าวไม่อยู่ในรายการไฟล์ปัจจุบันของ sandbox. Connection settings ถูกกำหนดใน source ไม่ควรรันกับ MinIO production. `result.jpg` และ `result(1).jpg` เป็นไฟล์ภาพที่อยู่ในโฟลเดอร์นี้; README ไม่ได้ยืนยันว่าเป็น output จากการรันครั้งใด.
