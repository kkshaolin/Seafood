#!/usr/bin/env python3
"""
ดาวน์โหลดชุดข้อมูลจาก Hugging Face แล้วส่งไฟล์ไปยัง MinIO

เป็นเครื่องมือให้ผู้ดูแลเรียกใช้เอง; Docker Compose และตัวแอปไม่ได้รันไฟล์นี้อัตโนมัติ
"""
import os
import argparse
from datasets import load_dataset
from minio import Minio
from minio.error import S3Error

def main():
    # รับชื่อชุดข้อมูลและ bucket จาก command line เพื่อกำหนดแหล่งและปลายทางตอนเรียก
    parser = argparse.ArgumentParser(description='Download dataset to MinIO')
    parser.add_argument('--dataset', type=str, required=True, 
                       help='Dataset name from Hugging Face (e.g., conll2003)')
    parser.add_argument('--bucket', type=str, default='training-data',
                       help='MinIO bucket name')
    
    args = parser.parse_args()
    
    # เชื่อมต่อ object storage ที่รองรับ S3 โดยอ่าน endpoint และ credentials จาก environment
    minio_client = Minio(
        os.getenv('MINIO_ENDPOINT', 'localhost:9000'),
        access_key=os.getenv('MINIO_ACCESS_KEY', 'admin'),
        secret_key=os.getenv('MINIO_SECRET_KEY', 'password123'),
        secure=False
    )
    
    # สร้าง bucket หากยังไม่มี เพื่อให้ขั้นตอนถัดไปเขียนไฟล์ได้
    if not minio_client.bucket_exists(args.bucket):
        minio_client.make_bucket(args.bucket)
        print(f"Created bucket: {args.bucket}")
    
    # ดาวน์โหลดข้อมูลและ metadata ด้วยไลบรารี Hugging Face Datasets
    print(f"Loading dataset: {args.dataset}")
    dataset = load_dataset(args.dataset)
    
    # บันทึกชุดข้อมูลลง disk ชั่วคราว เพราะ MinIO client อัปโหลดจาก path ของไฟล์
    local_path = f"/tmp/datasets/{args.dataset.replace('/', '_')}"
    dataset.save_to_disk(local_path)
    print(f"Saved dataset to: {local_path}")
    
    # อัปโหลดทุกไฟล์โดยคงโครงสร้าง path ย่อยไว้ใต้ prefix ของชุดข้อมูล
    print(f"Uploading to MinIO bucket: {args.bucket}")
    for root, dirs, files in os.walk(local_path):
        for file in files:
            local_file = os.path.join(root, file)
            object_name = f"datasets/{args.dataset.replace('/', '_')}/{os.path.relpath(local_file, local_path)}"
            
            minio_client.fput_object(
                args.bucket,
                object_name,
                local_file
            )
            print(f"  Uploaded: {object_name}")
    
    print("✅ Dataset uploaded successfully!")

if __name__ == "__main__":
    main()