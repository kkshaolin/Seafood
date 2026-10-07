#!/usr/bin/env python3
"""
Hugging Face Model Hub Synchronization Script (Hybrid Cache-Aside Pattern)
==========================================================================
Repo:     kkshaolin/yolo_box (Public)
Purpose:  Synchronize ML models (YOLO box detection and ARIMA demand forecasting)
          between local storage, MinIO Object Storage, and Hugging Face Hub.

Architecture (Hybrid Cache-Aside):
  1. Low-latency Runtime: Local storage (`storage/models/`) and MinIO bucket (`models`)
     provide <1ms inference speed for FastAPI and workers.
  2. Central Remote Registry: Hugging Face Model Hub (`kkshaolin/yolo_box`) serves as
     the authoritative versioned model repository for collaboration and initial seeding.
  3. Automatic Cache-Aside Seeding: When running on a fresh clone where local/MinIO
     models are missing, the system automatically pulls models from Hugging Face Hub.
"""

import os
import sys
import json
import argparse
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

# Setup logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("hf_sync")

# Load .env file if available
def load_dotenv_fallback():
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    candidates = [repo_root / ".env", Path(".env")]
    for env_path in candidates:
        if env_path.is_file():
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip("'\"")
                            if k not in os.environ:
                                os.environ[k] = v
                logger.debug(f"Loaded environment variables from {env_path}")
                break
            except Exception as e:
                logger.warning(f"Failed to read {env_path}: {e}")

load_dotenv_fallback()

# Resolve Paths
REPO_ROOT = Path(__file__).resolve().parent.parent
STORAGE_ROOT = Path(os.getenv("STORAGE_ROOT", str(REPO_ROOT / "storage")))
MODELS_DIR = STORAGE_ROOT / "models"
YOLO_LOCAL_PATH = MODELS_DIR / "non_time_serie" / "yolo11n.pt"
YOLO_V3_LOCAL_PATH = MODELS_DIR / "non_time_serie" / "yolo11n_v3.pt"
ARIMA_PKL_PATH = MODELS_DIR / "time_serie" / "arima_Frozen_Seafood.pkl"
ARIMA_JSON_PATH = MODELS_DIR / "time_serie" / "arima_Frozen_Seafood.json"

DEFAULT_HF_REPO = os.getenv("HF_REPO_ID", "kkshaolin/yolo_box")
DEFAULT_HF_TOKEN = os.getenv("HF_TOKEN", "")

# MinIO Config
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "admin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "password123")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"
MINIO_BUCKET = "models"


def get_minio_client():
    try:
        from minio import Minio
        client = Minio(
            endpoint=MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=MINIO_SECURE,
        )
        return client
    except Exception as e:
        logger.warning(f"MinIO client initialization failed ({MINIO_ENDPOINT}): {e}")
        return None


def generate_model_card() -> str:
    """Generate Hugging Face Model Card README.md."""
    metrics_info = "Metrics not found"
    if ARIMA_JSON_PATH.exists():
        try:
            m = json.loads(ARIMA_JSON_PATH.read_text(encoding="utf-8"))
            metrics_info = (
                f"- **Model Order**: `{m.get('model_order', 'ARIMA(2,0,2)')}`\n"
                f"- **MAE**: `{m.get('mae', 0):.2f}` boxes\n"
                f"- **RMSE**: `{m.get('rmse', 0):.2f}` boxes\n"
                f"- **MAPE**: `{m.get('mape', 0):.2f}%`\n"
                f"- **Trained At**: `{m.get('trained_at', 'N/A')}`\n"
                f"- **Training Months**: `{m.get('n_train_months', 70)}`"
            )
        except Exception:
            pass

    return f"""---
license: apache-2.0
tags:
- yolo
- object-detection
- arima
- time-series
- inventory-management
- seafood-logistics
---

# 📦 Seafood Inventory AI Models (Hybrid Cache-Aside Registry)

Central model repository for the **I_LoveSeafood AI Engineering Ecosystem**.

This repository hosts pre-trained model weights for:
1. **YOLO Box Detection (`yolo/yolo11n.pt`)**: Real-time seafood box detection from surveillance camera feeds (Zone A & Zone B).
2. **ARIMA Demand Forecasting (`arima/arima_Frozen_Seafood.pkl`)**: Optimal stock inventory prediction to maximize profit and prevent stockouts.

---

## 🚀 Architecture: Hybrid Cache-Aside

```mermaid
flowchart LR
    Dev["Developer / Worker"] -->|"1. Check Local/MinIO (<1ms)"| Local[("Local Storage / MinIO")]
    Local -.->|"2. Cache Miss"| HFHub[("🤗 Hugging Face Hub (kkshaolin/yolo_box)")]
    HFHub -->|"3. Auto-Pull & Seed"| Local
    Dev -->|"4. Publish Trained Model"| HFHub
```

- **Runtime Serving**: MinIO Object Storage and local container disk (`/app/storage/models/`) provide ultra-low latency (<1ms).
- **Remote Hub**: Hugging Face Hub (`kkshaolin/yolo_box`) provides reliable distributed storage and automated seeding for freshly cloned environments.

---

## 📊 Models in this Repository

### 1. YOLO11n Box Detection
- **File**: `yolo/yolo11n.pt`
- **Class**: `box` (Seafood transport container box)
- **Use Case**: Counting physical seafood boxes in cold storage camera feeds.

### 2. ARIMA Time Series Forecaster
- **Binary**: `arima/arima_Frozen_Seafood.pkl`
- **Metadata**: `arima/arima_Frozen_Seafood.json`
- **Product**: `Frozen_Seafood`
{metrics_info}

---

## 🛠️ How to Sync

### Synchronize locally:
```bash
# Pull latest models from Hugging Face into storage/models and MinIO:
python scripts/sync_huggingface.py --action pull

# Publish newly trained models to Hugging Face:
python scripts/sync_huggingface.py --action push
```

### Auto-seed on first run (Cache-Aside):
```bash
python scripts/sync_huggingface.py --action check-or-pull
```
"""


def get_hf_api(token: Optional[str] = None):
    try:
        from huggingface_hub import HfApi
        return HfApi(token=token or DEFAULT_HF_TOKEN)
    except ImportError:
        logger.error("huggingface_hub package is not installed. Run: pip install huggingface-hub")
        sys.exit(1)


def check_status(repo_id: str = DEFAULT_HF_REPO, token: Optional[str] = None) -> Dict[str, Any]:
    """Check status of local models, MinIO objects, and Hugging Face repository."""
    logger.info("=" * 60)
    logger.info(f"Checking Status: Hugging Face Model Hub ({repo_id})")
    logger.info("=" * 60)

    # 1. Local Files
    local_status = {
        "yolo_box_v3 (Recommended)": {
            "path": str(YOLO_V3_LOCAL_PATH),
            "exists": YOLO_V3_LOCAL_PATH.is_file(),
            "size_mb": round(YOLO_V3_LOCAL_PATH.stat().st_size / (1024 * 1024), 2) if YOLO_V3_LOCAL_PATH.is_file() else 0
        },
        "yolo_box": {
            "path": str(YOLO_LOCAL_PATH),
            "exists": YOLO_LOCAL_PATH.is_file(),
            "size_mb": round(YOLO_LOCAL_PATH.stat().st_size / (1024 * 1024), 2) if YOLO_LOCAL_PATH.is_file() else 0
        },
        "arima_pkl": {
            "path": str(ARIMA_PKL_PATH),
            "exists": ARIMA_PKL_PATH.is_file(),
            "size_kb": round(ARIMA_PKL_PATH.stat().st_size / 1024, 2) if ARIMA_PKL_PATH.is_file() else 0
        },
        "arima_json": {
            "path": str(ARIMA_JSON_PATH),
            "exists": ARIMA_JSON_PATH.is_file()
        }
    }
    logger.info("Local Storage:")
    for k, v in local_status.items():
        exists_mark = "✅ Found" if v["exists"] else "❌ Missing"
        info = f"{v.get('size_mb', v.get('size_kb', ''))} {'MB' if 'size_mb' in v else 'KB'}" if v["exists"] and ("size_mb" in v or "size_kb" in v) else ""
        logger.info(f"  - {k}: {exists_mark} ({info}) -> {v.get('path', '')}")

    # 2. MinIO Objects
    minio_status = {"connected": False, "objects": []}
    minio_client = get_minio_client()
    if minio_client:
        try:
            if minio_client.bucket_exists(MINIO_BUCKET):
                objects = [o.object_name for o in minio_client.list_objects(MINIO_BUCKET, recursive=True)]
                minio_status = {"connected": True, "objects": objects}
                logger.info(f"MinIO Bucket '{MINIO_BUCKET}': ✅ Connected ({len(objects)} objects found)")
                for obj in objects[:5]:
                    logger.info(f"  - s3://{MINIO_BUCKET}/{obj}")
                if len(objects) > 5:
                    logger.info(f"  - ... and {len(objects) - 5} more")
            else:
                logger.info(f"MinIO Bucket '{MINIO_BUCKET}': ⚠️ Bucket does not exist yet")
        except Exception as e:
            logger.warning(f"MinIO check error: {e}")

    # 3. Hugging Face Hub
    hf_status = {"connected": False, "repo_exists": False, "files": [], "user": None}
    try:
        api = get_hf_api(token)
        who = None
        try:
            who = api.whoami().get("name")
            hf_status["user"] = who
        except Exception:
            pass

        files = api.list_repo_files(repo_id=repo_id, repo_type="model")
        hf_status["connected"] = True
        hf_status["repo_exists"] = True
        hf_status["files"] = files
        logger.info(f"Hugging Face Hub ('{repo_id}'): ✅ Connected (Auth: {who or 'Anonymous'})")
        logger.info(f"  Remote Files ({len(files)}):")
        for f in files:
            logger.info(f"    - {f}")
    except Exception as e:
        logger.warning(f"Hugging Face check error: {e}")

    logger.info("=" * 60)
    return {
        "repo_id": repo_id,
        "local": local_status,
        "minio": minio_status,
        "huggingface": hf_status
    }


def push_to_huggingface(repo_id: str = DEFAULT_HF_REPO, token: Optional[str] = None, sync_minio: bool = True) -> bool:
    """Push local models to Hugging Face Model Hub and optionally sync to MinIO."""
    logger.info(f"Starting Push to Hugging Face: {repo_id}")
    active_token = token or DEFAULT_HF_TOKEN
    if not active_token:
        logger.error("Hugging Face token is required for push operations! Set HF_TOKEN in .env or pass --token")
        return False

    api = get_hf_api(active_token)

    # Ensure repository exists
    try:
        api.create_repo(repo_id=repo_id, repo_type="model", private=False, exist_ok=True)
        logger.info(f"Repository {repo_id} verified / ready (Public).")
    except Exception as e:
        logger.error(f"Failed to verify/create repository {repo_id}: {e}")
        return False

    uploaded_files = []

    # 1. Upload Recommended YOLO v3 model (yolo11n_v3.pt)
    if YOLO_V3_LOCAL_PATH.is_file():
        logger.info(f"Uploading recommended YOLO v3 weights: {YOLO_V3_LOCAL_PATH} -> {repo_id}:yolo/yolo11n_v3.pt")
        try:
            api.upload_file(
                path_or_fileobj=str(YOLO_V3_LOCAL_PATH),
                path_in_repo="yolo/yolo11n_v3.pt",
                repo_id=repo_id,
                repo_type="model",
                commit_message="Add recommended YOLO11n v3 seafood box detection weights"
            )
            uploaded_files.append("yolo/yolo11n_v3.pt")
            logger.info("✅ Recommended YOLO v3 model uploaded successfully.")
        except Exception as e:
            logger.error(f"❌ Failed to upload recommended YOLO v3 weights: {e}")
    else:
        logger.warning(f"⚠️ Recommended YOLO v3 model file not found at {YOLO_V3_LOCAL_PATH}, skipping.")

    # 1b. Upload Base YOLO model (yolo11n.pt) if present
    if YOLO_LOCAL_PATH.is_file():
        logger.info(f"Uploading YOLO weights: {YOLO_LOCAL_PATH} -> {repo_id}:yolo/yolo11n.pt")
        try:
            api.upload_file(
                path_or_fileobj=str(YOLO_LOCAL_PATH),
                path_in_repo="yolo/yolo11n.pt",
                repo_id=repo_id,
                repo_type="model",
                commit_message="Update YOLO11n seafood box detection weights"
            )
            uploaded_files.append("yolo/yolo11n.pt")
            logger.info("✅ YOLO model uploaded successfully.")
        except Exception as e:
            logger.error(f"❌ Failed to upload YOLO weights: {e}")
    else:
        logger.warning(f"⚠️ YOLO model file not found at {YOLO_LOCAL_PATH}, skipping.")

    # 2. Upload ARIMA model .pkl
    if ARIMA_PKL_PATH.is_file():
        logger.info(f"Uploading ARIMA pickle: {ARIMA_PKL_PATH} -> {repo_id}:arima/arima_Frozen_Seafood.pkl")
        try:
            api.upload_file(
                path_or_fileobj=str(ARIMA_PKL_PATH),
                path_in_repo="arima/arima_Frozen_Seafood.pkl",
                repo_id=repo_id,
                repo_type="model",
                commit_message="Update ARIMA(2,0,2) Frozen Seafood demand forecast model"
            )
            uploaded_files.append("arima/arima_Frozen_Seafood.pkl")
            logger.info("✅ ARIMA model pickle uploaded successfully.")
        except Exception as e:
            logger.error(f"❌ Failed to upload ARIMA model pickle: {e}")
    else:
        logger.warning(f"⚠️ ARIMA model pickle not found at {ARIMA_PKL_PATH}, skipping.")

    # 3. Upload ARIMA metrics .json
    if ARIMA_JSON_PATH.is_file():
        logger.info(f"Uploading ARIMA metrics: {ARIMA_JSON_PATH} -> {repo_id}:arima/arima_Frozen_Seafood.json")
        try:
            api.upload_file(
                path_or_fileobj=str(ARIMA_JSON_PATH),
                path_in_repo="arima/arima_Frozen_Seafood.json",
                repo_id=repo_id,
                repo_type="model",
                commit_message="Update ARIMA(2,0,2) evaluation metrics"
            )
            uploaded_files.append("arima/arima_Frozen_Seafood.json")
            logger.info("✅ ARIMA metrics uploaded successfully.")
        except Exception as e:
            logger.error(f"❌ Failed to upload ARIMA metrics: {e}")

    # 4. Upload Model Card README.md
    readme_content = generate_model_card()
    try:
        readme_bytes = readme_content.encode("utf-8")
        api.upload_file(
            path_or_fileobj=readme_bytes,
            path_in_repo="README.md",
            repo_id=repo_id,
            repo_type="model",
            commit_message="Update Model Card documentation and metrics"
        )
        uploaded_files.append("README.md")
        logger.info("✅ Model Card README.md uploaded successfully.")
    except Exception as e:
        logger.warning(f"Failed to upload README.md: {e}")

    # 5. Sync to MinIO if requested
    if sync_minio:
        seed_to_minio()

    logger.info("=" * 60)
    logger.info(f"Push completed! Uploaded {len(uploaded_files)} files to Hugging Face Hub ({repo_id}).")
    logger.info("=" * 60)
    return len(uploaded_files) > 0


def pull_from_huggingface(repo_id: str = DEFAULT_HF_REPO, token: Optional[str] = None, sync_minio: bool = True, force: bool = False) -> bool:
    """Pull models from Hugging Face Hub down to local storage and seed MinIO."""
    logger.info(f"Starting Pull from Hugging Face Hub: {repo_id}")
    active_token = token or DEFAULT_HF_TOKEN or None
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        logger.error("huggingface_hub package is not installed.")
        return False

    # Ensure target directories exist
    YOLO_LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARIMA_PKL_PATH.parent.mkdir(parents=True, exist_ok=True)

    files_to_download = [
        ("yolo/yolo11n_v3.pt", YOLO_V3_LOCAL_PATH),
        ("yolo/yolo11n.pt", YOLO_LOCAL_PATH),
        ("arima/arima_Frozen_Seafood.pkl", ARIMA_PKL_PATH),
        ("arima/arima_Frozen_Seafood.json", ARIMA_JSON_PATH),
    ]

    success_count = 0
    for hf_filename, local_dest in files_to_download:
        if local_dest.is_file() and not force:
            logger.info(f"Local file already exists: {local_dest} (use --force to overwrite)")
            success_count += 1
            continue

        try:
            logger.info(f"Downloading from HF Hub: {repo_id}:{hf_filename} -> {local_dest}")
            downloaded_path = hf_hub_download(
                repo_id=repo_id,
                filename=hf_filename,
                token=active_token,
                local_dir=str(STORAGE_ROOT / "models_temp"),
            )
            # Copy or move to final destination
            import shutil
            shutil.copy2(downloaded_path, str(local_dest))
            logger.info(f"✅ Successfully downloaded {hf_filename} -> {local_dest}")
            success_count += 1
        except Exception as e:
            logger.warning(f"Could not download {hf_filename} from {repo_id}: {e}")

    # Clean up temp folder
    temp_dir = STORAGE_ROOT / "models_temp"
    if temp_dir.exists():
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

    # Seed to MinIO
    if sync_minio:
        seed_to_minio()

    logger.info("=" * 60)
    logger.info(f"Pull completed! {success_count}/{len(files_to_download)} files ready in local storage.")
    logger.info("=" * 60)
    return success_count > 0


def seed_to_minio():
    """Upload existing local models into MinIO bucket 'models'."""
    client = get_minio_client()
    if not client:
        logger.info("Skipping MinIO sync (MinIO unreachable).")
        return

    try:
        if not client.bucket_exists(MINIO_BUCKET):
            client.make_bucket(MINIO_BUCKET)
            logger.info(f"Created MinIO bucket '{MINIO_BUCKET}'")

        # 1. Recommended YOLO v3 Model (delivery_box)
        if YOLO_V3_LOCAL_PATH.is_file():
            for key in ["yolo/yolo11n_v3.pt", "yolo/recommended/yolo11n_v3.pt", "yolo/base/yolo11n_v3.pt"]:
                client.fput_object(MINIO_BUCKET, key, str(YOLO_V3_LOCAL_PATH))
                logger.info(f"✅ Synced to MinIO: s3://{MINIO_BUCKET}/{key}")

        # 1b. Base YOLO Model (yolo11n.pt)
        if YOLO_LOCAL_PATH.is_file():
            key = "yolo/base/yolo11n.pt"
            client.fput_object(MINIO_BUCKET, key, str(YOLO_LOCAL_PATH))
            logger.info(f"✅ Synced to MinIO: s3://{MINIO_BUCKET}/{key}")

        # 2. ARIMA Model
        if ARIMA_PKL_PATH.is_file():
            key = "arima/Frozen_Seafood/latest/model.pkl"
            client.fput_object(MINIO_BUCKET, key, str(ARIMA_PKL_PATH))
            logger.info(f"✅ Synced to MinIO: s3://{MINIO_BUCKET}/{key}")

        # 3. ARIMA Metrics
        if ARIMA_JSON_PATH.is_file():
            key = "arima/Frozen_Seafood/latest/metrics.json"
            client.fput_object(MINIO_BUCKET, key, str(ARIMA_JSON_PATH))
            logger.info(f"✅ Synced to MinIO: s3://{MINIO_BUCKET}/{key}")

    except Exception as e:
        logger.warning(f"MinIO seed warning: {e}")


def check_or_pull(repo_id: str = DEFAULT_HF_REPO, token: Optional[str] = None):
    """Hybrid Cache-Aside: check if local models exist; if missing, pull from HF."""
    logger.info("Checking local model cache...")
    missing = []
    if not YOLO_V3_LOCAL_PATH.is_file():
        missing.append("yolo11n_v3.pt")
    if not ARIMA_PKL_PATH.is_file():
        missing.append("arima_Frozen_Seafood.pkl")

    if missing:
        logger.info(f"Cache miss! Missing local models: {missing}. Pulling from Hugging Face Model Hub...")
        pull_from_huggingface(repo_id=repo_id, token=token, sync_minio=True, force=False)
    else:
        logger.info("Cache hit! All required local models exist.")
        # Ensure MinIO is populated
        seed_to_minio()


def main():
    parser = argparse.ArgumentParser(description="Hugging Face Model Hub Synchronization (Hybrid Cache-Aside)")
    parser.add_argument(
        "--action",
        choices=["status", "push", "pull", "check-or-pull"],
        default="status",
        help="Action to perform: status, push, pull, or check-or-pull"
    )
    parser.add_argument("--repo-id", default=DEFAULT_HF_REPO, help=f"Hugging Face repository ID (default: {DEFAULT_HF_REPO})")
    parser.add_argument("--token", default=None, help="Hugging Face User Access Token (defaults to HF_TOKEN from env)")
    parser.add_argument("--skip-minio", action="store_true", help="Skip syncing models into MinIO")
    parser.add_argument("--force", action="store_true", help="Force overwrite local files during pull")

    args = parser.parse_args()

    if args.action == "status":
        check_status(repo_id=args.repo_id, token=args.token)
    elif args.action == "push":
        success = push_to_huggingface(repo_id=args.repo_id, token=args.token, sync_minio=not args.skip_minio)
        sys.exit(0 if success else 1)
    elif args.action == "pull":
        success = pull_from_huggingface(repo_id=args.repo_id, token=args.token, sync_minio=not args.skip_minio, force=args.force)
        sys.exit(0 if success else 1)
    elif args.action == "check-or-pull":
        check_or_pull(repo_id=args.repo_id, token=args.token)


if __name__ == "__main__":
    main()
