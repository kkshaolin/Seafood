import os
from minio import Minio

# 1. ตั้งค่าการเชื่อมต่อ MinIO
client = Minio(
    "localhost:9000",
    access_key="admin",
    secret_key="password123",
    secure=False
)

# 2. เช็กว่ามี Bucket 'models' หรือยัง
if not client.bucket_exists("models"):
    client.make_bucket("models")

# 3. ระบุพิกัดไฟล์โมเดล (ที่เอามาวางและเปลี่ยนชื่อเรียบร้อยแล้ว)
source_file = r"C:\Users\student\Desktop\faii\Seafood\storage\models\non_time_serie\yolo11n.pt"

if os.path.exists(source_file):
    # 4. อัปโหลดขึ้น MinIO
    minio_dest = "yolo/base/yolo11n.pt"
    client.fput_object("models", minio_dest, source_file)
    print(f"✅ อัปโหลดขึ้น MinIO ที่ {minio_dest} สำเร็จ!")
    print("\n🎉 พร้อมใช้งาน! ไปรีสตาร์ท Docker ได้เลยครับ")
else:
    print(f"❌ หาไฟล์โมเดลไม่เจอ เช็กดูว่าอยู่ใน {source_file} จริงไหมครับ")