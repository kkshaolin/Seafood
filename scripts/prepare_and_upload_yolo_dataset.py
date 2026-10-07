#!/usr/bin/env python3
"""
Prepare YOLO Dataset Splits (Train / Val / Test) and Upload to MinIO
===================================================================
1. Takes 59 ground-truth images and labels from storage/data/warehouse_box_dataset/
2. Splits deterministically (seed=42):
   - Train: 41 images (~70%)
   - Val:   9 images (~15%)
   - Test:  9 images (~15%)
3. Places files in:
   - storage/data/warehouse_box_dataset/train/{images,labels}
   - storage/data/warehouse_box_dataset/valid/{images,labels}
   - storage/data/warehouse_box_dataset/test/{images,labels}
4. Packages a clean YOLO dataset zip: box_v1.zip
5. Uploads box_v1.zip to MinIO bucket 'datasets':
   - yolo/box_v1/box_v1.zip
   - yolo/box_v1.zip
   - yolo/warehouse_box_dataset/warehouse_box_dataset.zip
"""

import os
import sys
import shutil
import random
import zipfile
from pathlib import Path
from minio import Minio

REPO_ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = REPO_ROOT / "storage" / "data" / "warehouse_box_dataset"
IMAGES_DIR = DATASET_DIR / "images"
LABELS_DIR = DATASET_DIR / "labels"

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "admin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "password123")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"
BUCKET_NAME = "datasets"


def prepare_splits():
    print(f"[*] Reading dataset from {DATASET_DIR}...")
    if not IMAGES_DIR.is_dir() or not LABELS_DIR.is_dir():
        raise FileNotFoundError(f"Missing images or labels directory in {DATASET_DIR}")

    img_files = sorted([f for f in IMAGES_DIR.iterdir() if f.suffix.lower() in {".png", ".jpg", ".jpeg"}])
    pairs = []
    for img in img_files:
        lbl = LABELS_DIR / f"{img.stem}.txt"
        if lbl.is_file():
            pairs.append((img, lbl))
        else:
            print(f"[!] Warning: Missing label for image {img.name}")

    print(f"[*] Found {len(pairs)} matched image-label pairs.")
    if len(pairs) == 0:
        raise ValueError("No matched pairs found!")

    # Deterministic shuffle
    random.seed(42)
    shuffled = pairs.copy()
    random.shuffle(shuffled)

    # 41 train, 9 val, 9 test
    train_pairs = shuffled[:41]
    val_pairs = shuffled[41:50]
    test_pairs = shuffled[50:]

    print(f"[*] Split counts: Train={len(train_pairs)}, Val={len(val_pairs)}, Test={len(test_pairs)}")

    splits = {
        "train": train_pairs,
        "valid": val_pairs,
        "test": test_pairs,
    }

    for split_name, pair_list in splits.items():
        s_img_dir = DATASET_DIR / split_name / "images"
        s_lbl_dir = DATASET_DIR / split_name / "labels"
        s_img_dir.mkdir(parents=True, exist_ok=True)
        s_lbl_dir.mkdir(parents=True, exist_ok=True)

        for img_path, lbl_path in pair_list:
            dest_img = s_img_dir / img_path.name
            dest_lbl = s_lbl_dir / lbl_path.name
            shutil.copy2(img_path, dest_img)
            shutil.copy2(lbl_path, dest_lbl)

        print(f"[+] Populated {split_name}: {len(pair_list)} images and labels.")

    # Ensure data.yaml is up to date
    yaml_content = """# Dataset configuration for delivery_box YOLO detection
path: ./storage/data/warehouse_box_dataset
train: train/images
val: valid/images
test: test/images

nc: 1
names: ['delivery_box']
"""
    data_yaml_path = DATASET_DIR / "data.yaml"
    with open(data_yaml_path, "w", encoding="utf-8") as f:
        f.write(yaml_content)
    print(f"[+] Updated {data_yaml_path}")

    # Ensure classes.txt
    classes_path = DATASET_DIR / "classes.txt"
    with open(classes_path, "w", encoding="utf-8") as f:
        f.write("delivery_box\n")
    print(f"[+] Verified {classes_path}")

    return splits


def create_zip():
    zip_path = REPO_ROOT / "storage" / "data" / "box_v1.zip"
    print(f"[*] Creating archive: {zip_path}...")

    # We package train, valid, test, data.yaml, classes.txt, notes.json into the root of zip
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for split in ["train", "valid", "test"]:
            for folder in ["images", "labels"]:
                dir_to_walk = DATASET_DIR / split / folder
                for f in dir_to_walk.iterdir():
                    arcname = f"{split}/{folder}/{f.name}"
                    zf.write(f, arcname)

        if (DATASET_DIR / "data.yaml").is_file():
            zf.write(DATASET_DIR / "data.yaml", "data.yaml")
        if (DATASET_DIR / "classes.txt").is_file():
            zf.write(DATASET_DIR / "classes.txt", "classes.txt")
        if (DATASET_DIR / "notes.json").is_file():
            zf.write(DATASET_DIR / "notes.json", "notes.json")

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"[+] Created {zip_path} ({size_mb:.2f} MB)")
    return zip_path


def upload_to_minio(zip_path: Path):
    print(f"[*] Connecting to MinIO at {MINIO_ENDPOINT}...")
    client = Minio(
        endpoint=MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE,
    )

    if not client.bucket_exists(BUCKET_NAME):
        client.make_bucket(BUCKET_NAME)
        print(f"[+] Created bucket {BUCKET_NAME}")

    upload_targets = [
        "yolo/box_v1/box_v1.zip",
        "yolo/box_v1.zip",
        "yolo/warehouse_box_dataset/warehouse_box_dataset.zip",
    ]

    for key in upload_targets:
        print(f"[*] Uploading to {BUCKET_NAME}/{key}...")
        client.fput_object(
            bucket_name=BUCKET_NAME,
            object_name=key,
            file_path=str(zip_path),
            content_type="application/zip",
        )
        print(f"[+] Successfully uploaded {BUCKET_NAME}/{key}")


if __name__ == "__main__":
    prepare_splits()
    zip_path = create_zip()
    upload_to_minio(zip_path)
    print("\n[SUCCESS] YOLO Dataset split and MinIO upload completed!")
