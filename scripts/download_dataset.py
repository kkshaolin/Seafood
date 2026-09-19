#!/usr/bin/env python3
"""
Script สำหรับโหลด dataset จาก Hugging Face และเก็บใน MinIO
"""
import os
import argparse
from datasets import load_dataset
from minio import Minio
from minio.error import S3Error

def main():
    parser = argparse.ArgumentParser(description='Download dataset to MinIO')
    parser.add_argument('--dataset', type=str, required=True, 
                       help='Dataset name from Hugging Face (e.g., conll2003)')
    parser.add_argument('--bucket', type=str, default='training-data',
                       help='MinIO bucket name')
    
    args = parser.parse_args()
    
    # Initialize MinIO client
    minio_client = Minio(
        os.getenv('MINIO_ENDPOINT', 'localhost:9000'),
        access_key=os.getenv('MINIO_ACCESS_KEY', 'minioadmin'),
        secret_key=os.getenv('MINIO_SECRET_KEY', 'minioadmin'),
        secure=False
    )
    
    # Create bucket if not exists
    if not minio_client.bucket_exists(args.bucket):
        minio_client.make_bucket(args.bucket)
        print(f"Created bucket: {args.bucket}")
    
    # Load dataset
    print(f"Loading dataset: {args.dataset}")
    dataset = load_dataset(args.dataset)
    
    # Save locally first
    local_path = f"/tmp/datasets/{args.dataset.replace('/', '_')}"
    dataset.save_to_disk(local_path)
    print(f"Saved dataset to: {local_path}")
    
    # Upload to MinIO
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