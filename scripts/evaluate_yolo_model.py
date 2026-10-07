#!/usr/bin/env python3
"""
YOLO Model Evaluation Script (Strict Ground-Truth Validation)
=============================================================
Evaluates YOLO model (default: yolo11n_v3.pt) against a real held-out test set.

Strict Quality & Integrity Rules:
1. NEVER use synthetic, mock, or unlabelled video data to fabricate accuracy metrics.
2. Only evaluate on genuine held-out test sets with ground-truth YOLO labels.
3. If no ground-truth test dataset is available, explicitly report status as
   'ยังประเมินไม่ได้' (Not Evaluatable Yet) and detail the required dataset specifications.
4. Report model version, SHA256 checksum, and class mappings.
"""

import os
import sys
import json
import hashlib
import argparse
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("yolo_eval")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL_PATH = REPO_ROOT / "storage" / "models" / "non_time_serie" / "yolo11n_v3.pt"
DEFAULT_DATA_YAML = REPO_ROOT / "storage" / "data" / "warehouse_box_dataset" / "data.yaml"


def compute_sha256(filepath: Path) -> str:
    """Compute SHA256 hash of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def verify_test_dataset(data_yaml_path: Path) -> Dict[str, Any]:
    """Inspect dataset configuration and verify physical presence of held-out test images and labels."""
    if not data_yaml_path.is_file():
        return {
            "valid": False,
            "reason": f"data.yaml not found at {data_yaml_path}",
            "image_count": 0,
            "label_count": 0
        }

    import yaml
    try:
        with open(data_yaml_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
    except Exception as e:
        return {
            "valid": False,
            "reason": f"Could not parse data.yaml: {e}",
            "image_count": 0,
            "label_count": 0
        }

    dataset_root = data_yaml_path.parent
    test_rel = cfg.get("test") or cfg.get("val")

    if not test_rel:
        return {
            "valid": False,
            "reason": "Neither 'test' nor 'val' path specified in data.yaml",
            "image_count": 0,
            "label_count": 0
        }

    test_images_dir = (dataset_root / test_rel).resolve()
    if not test_images_dir.exists():
        # Try relative to repo root
        test_images_dir = (REPO_ROOT / test_rel).resolve()

    if not test_images_dir.is_dir():
        return {
            "valid": False,
            "reason": f"Test images directory does not exist: {test_images_dir}",
            "image_count": 0,
            "label_count": 0,
            "expected_dir": str(test_images_dir)
        }

    # Search for image files
    image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    images = [p for p in test_images_dir.iterdir() if p.suffix.lower() in image_exts]
    image_count = len(images)

    # Search for matching labels
    test_labels_dir = test_images_dir.parent / "labels"
    label_count = 0
    valid_box_count = 0
    if test_labels_dir.is_dir():
        for img in images:
            lbl_file = test_labels_dir / f"{img.stem}.txt"
            if lbl_file.is_file() and lbl_file.stat().st_size > 0:
                label_count += 1
                try:
                    with open(lbl_file, "r", encoding="utf-8") as lf:
                        lines = [l.strip() for l in lf if l.strip()]
                        valid_box_count += len(lines)
                except Exception:
                    pass

    return {
        "valid": image_count > 0 and label_count > 0,
        "images_dir": str(test_images_dir),
        "labels_dir": str(test_labels_dir),
        "image_count": image_count,
        "label_count": label_count,
        "valid_box_count": valid_box_count,
        "classes": cfg.get("names", []),
        "num_classes": cfg.get("nc", 1),
    }


def evaluate_model(
    model_path: Path = DEFAULT_MODEL_PATH,
    data_yaml_path: Path = DEFAULT_DATA_YAML,
    conf_threshold: float = 0.25,
    iou_threshold: float = 0.60
) -> Dict[str, Any]:
    """Evaluate YOLO model on real held-out test set or report status clearly."""
    logger.info("=" * 70)
    logger.info("YOLO Model Evaluation & Integrity Verification")
    logger.info("=" * 70)

    # 1. Model Check
    if not model_path.is_file():
        logger.error(f"Model file not found at: {model_path}")
        return {
            "status": "error",
            "message": f"Model file not found at {model_path}"
        }

    sha256_hash = compute_sha256(model_path)
    file_size_mb = round(model_path.stat().st_size / (1024 * 1024), 2)
    logger.info(f"Model File:     {model_path.name} ({file_size_mb} MB)")
    logger.info(f"Model Path:     {model_path}")
    logger.info(f"SHA-256 Hash:   {sha256_hash}")

    from ultralytics import YOLO
    try:
        model = YOLO(str(model_path))
        class_names = model.names
        logger.info(f"Class Names:    {class_names}")
    except Exception as e:
        logger.error(f"Failed to load YOLO model: {e}")
        return {
            "status": "error",
            "message": f"Failed to load YOLO model: {e}"
        }

    # 2. Dataset Verification
    ds_check = verify_test_dataset(data_yaml_path)
    logger.info(f"Dataset YAML:   {data_yaml_path}")
    logger.info(f"Test Images:    {ds_check.get('image_count', 0)} found")
    logger.info(f"Test Labels:    {ds_check.get('label_count', 0)} matching label files found")

    # 3. Decision: Real Evaluation vs Honest 'ยังประเมินไม่ได้' Report
    if not ds_check["valid"]:
        logger.warning("-" * 70)
        logger.warning("สถานะผลประเมิน: ยังประเมินไม่ได้ (Not Evaluatable Yet)")
        logger.warning("เหตุผล: ไม่มี Ground-Truth Labeled Test Set ในพื้นที่จัดเก็บ")
        logger.warning("คำเตือนความถูกต้อง (Integrity Policy):")
        logger.warning("  - ห้ามสร้างตัวเลข mock/dummy accuracy เพื่อรายงานความถูกต้องของโมเดลจริง")
        logger.warning("  - ข้อมูล mock video (mockA.mp4, mockB.mp4) ไม่มี ground-truth bounding box labels")
        logger.warning("-" * 70)
        logger.warning("สิ่งที่ต้องเตรียมเพื่อประเมินความแม่นยำ:")
        logger.warning(f"  1. รูปภาพ held-out test set จัดเก็บใน: {ds_check.get('images_dir', 'test/images')}")
        logger.warning(f"  2. ไฟล์ annotation (.txt) จัดเก็บใน: {ds_check.get('labels_dir', 'test/labels')}")
        logger.warning("  3. ฟอร์แมต YOLO: <class_id> <x_center> <y_center> <width> <height> (class 0: delivery_box)")
        logger.warning("  4. สามารถ export dataset จาก Label Studio (http://localhost:8080) มาไว้ใน storage/data ได้")
        logger.warning("=" * 70)

        return {
            "status": "ยังประเมินไม่ได้",
            "reason": "Missing labeled held-out test set",
            "model_info": {
                "model_name": model_path.name,
                "model_path": str(model_path),
                "sha256": sha256_hash,
                "size_mb": file_size_mb,
                "classes": class_names,
            },
            "dataset_info": {
                "data_yaml": str(data_yaml_path),
                "images_found": ds_check.get("image_count", 0),
                "labels_found": ds_check.get("label_count", 0),
                "requirements": [
                    "Held-out test images with ground-truth .txt labels",
                    "Normalized bbox coordinates (class_id x_center y_center width height)",
                    "Single class mapping: 0 -> delivery_box"
                ]
            },
            "metrics": {
                "precision": None,
                "recall": None,
                "mAP50": None,
                "mAP50_95": None,
                "evaluation_note": "Accuracy cannot be computed without verified ground-truth labels."
            }
        }

    # 4. If genuine labeled held-out test set exists, run actual validation
    logger.info("Running validation on held-out test set...")
    val_results = model.val(
        data=str(data_yaml_path),
        split="test",
        conf=conf_threshold,
        iou=iou_threshold,
        verbose=True
    )

    metrics = {
        "precision": float(val_results.box.mp),
        "recall": float(val_results.box.mr),
        "mAP50": float(val_results.box.map50),
        "mAP50_95": float(val_results.box.map),
    }

    logger.info("=" * 70)
    logger.info("EVALUATION RESULTS (Held-Out Test Set):")
    logger.info(f"  Precision:  {metrics['precision']:.4f}")
    logger.info(f"  Recall:     {metrics['recall']:.4f}")
    logger.info(f"  mAP@50:     {metrics['mAP50']:.4f}")
    logger.info(f"  mAP@50-95:  {metrics['mAP50_95']:.4f}")
    logger.info("=" * 70)

    return {
        "status": "ประเมินเสร็จสมบูรณ์",
        "model_info": {
            "model_name": model_path.name,
            "sha256": sha256_hash,
            "size_mb": file_size_mb,
            "classes": class_names
        },
        "dataset_info": {
            "data_yaml": str(data_yaml_path),
            "test_images": ds_check["image_count"],
            "test_labels": ds_check["label_count"],
            "total_boxes": ds_check.get("valid_box_count", 0),
        },
        "metrics": metrics
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate YOLO Box Detection Model with Strict Integrity")
    parser.add_argument("--model", type=str, default=str(DEFAULT_MODEL_PATH), help="Path to model weights .pt")
    parser.add_argument("--data", type=str, default=str(DEFAULT_DATA_YAML), help="Path to data.yaml")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    args = parser.parse_args()

    res = evaluate_model(
        model_path=Path(args.model),
        data_yaml_path=Path(args.data)
    )

    if args.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
