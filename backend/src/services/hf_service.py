"""บริการสำหรับจัดการโมเดลบน Hugging Face Model Hub (Hybrid Cache-Aside Pattern).

ทำหน้าที่เชื่อมต่อกับ Hugging Face API สำหรับตรวจสอบสถานะ, อัปโหลดโมเดล (Push)
และดาวน์โหลดโมเดล (Pull) ลง storage/models และ MinIO.
"""

import os
import json
import shutil
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

from core.config import settings
from utils.logger import get_logger

logger = get_logger("hf_service")


class HuggingFaceService:
    def __init__(self):
        self.repo_id = os.getenv("HF_REPO_ID", settings.HF_REPO_ID or "kkshaolin/yolo_box")
        self.token = os.getenv("HF_TOKEN", settings.HF_TOKEN or "")
        
        # Paths
        storage_env = os.getenv("STORAGE_ROOT", "/app/storage")
        self.storage_root = Path(storage_env)
        if not self.storage_root.exists():
            # Fallback for host development
            repo_root = Path(__file__).resolve().parents[3]
            if (repo_root / "storage").exists():
                self.storage_root = repo_root / "storage"

        self.models_dir = self.storage_root / "models"
        self.yolo_path = self.models_dir / "non_time_serie" / "yolo11n.pt"
        self.arima_pkl_path = self.models_dir / "time_serie" / "arima_Frozen_Seafood.pkl"
        self.arima_json_path = self.models_dir / "time_serie" / "arima_Frozen_Seafood.json"

    def _get_api(self):
        from huggingface_hub import HfApi
        return HfApi(token=self.token if self.token else None)

    def _get_minio_client(self):
        try:
            from minio import Minio
            return Minio(
                endpoint=settings.MINIO_ENDPOINT,
                access_key=settings.MINIO_ACCESS_KEY,
                secret_key=settings.MINIO_SECRET_KEY,
                secure=settings.MINIO_SECURE,
            )
        except Exception as e:
            logger.warning(f"MinIO client init warning: {e}")
            return None

    def get_status(self) -> Dict[str, Any]:
        """ตรวจสอบสถานะโมเดลใน Local Storage, MinIO และ Hugging Face Hub"""
        # 1. Local
        local_info = {
            "yolo_box": {
                "name": "yolo11n.pt",
                "path": str(self.yolo_path),
                "exists": self.yolo_path.is_file(),
                "size_mb": round(self.yolo_path.stat().st_size / (1024 * 1024), 2) if self.yolo_path.is_file() else 0,
            },
            "arima_model": {
                "name": "arima_Frozen_Seafood.pkl",
                "path": str(self.arima_pkl_path),
                "exists": self.arima_pkl_path.is_file(),
                "size_kb": round(self.arima_pkl_path.stat().st_size / 1024, 2) if self.arima_pkl_path.is_file() else 0,
            },
            "arima_metrics": {
                "name": "arima_Frozen_Seafood.json",
                "path": str(self.arima_json_path),
                "exists": self.arima_json_path.is_file(),
            }
        }

        # 2. Hugging Face
        hf_info = {
            "repo_id": self.repo_id,
            "connected": False,
            "user": None,
            "files": [],
            "error": None
        }
        try:
            api = self._get_api()
            try:
                who = api.whoami()
                hf_info["user"] = who.get("name")
            except Exception:
                pass

            files = api.list_repo_files(repo_id=self.repo_id, repo_type="model")
            hf_info["connected"] = True
            hf_info["files"] = files
        except Exception as e:
            hf_info["error"] = str(e)

        # 3. MinIO
        minio_info = {"connected": False, "bucket": "models", "objects_count": 0}
        minio_client = self._get_minio_client()
        if minio_client:
            try:
                if minio_client.bucket_exists("models"):
                    objs = list(minio_client.list_objects("models", recursive=True))
                    minio_info["connected"] = True
                    minio_info["objects_count"] = len(objs)
            except Exception as e:
                minio_info["error"] = str(e)

        return {
            "repo_id": self.repo_id,
            "architecture": "Hybrid Cache-Aside",
            "local": local_info,
            "huggingface": hf_info,
            "minio": minio_info,
        }

    def push_models(self) -> Dict[str, Any]:
        """อัปโหลดโมเดลจาก local storage ไปยัง Hugging Face Model Hub และ MinIO"""
        if not self.token:
            raise ValueError("HF_TOKEN is required for pushing models to Hugging Face Hub.")

        api = self._get_api()
        api.create_repo(repo_id=self.repo_id, repo_type="model", private=False, exist_ok=True)

        uploaded = []

        # 1. YOLO
        if self.yolo_path.is_file():
            api.upload_file(
                path_or_fileobj=str(self.yolo_path),
                path_in_repo="yolo/yolo11n.pt",
                repo_id=self.repo_id,
                repo_type="model",
                commit_message="Update YOLO11n seafood box detection model"
            )
            uploaded.append("yolo/yolo11n.pt")

        # 2. ARIMA PKL
        if self.arima_pkl_path.is_file():
            api.upload_file(
                path_or_fileobj=str(self.arima_pkl_path),
                path_in_repo="arima/arima_Frozen_Seafood.pkl",
                repo_id=self.repo_id,
                repo_type="model",
                commit_message="Update ARIMA(2,0,2) Frozen Seafood forecast model"
            )
            uploaded.append("arima/arima_Frozen_Seafood.pkl")

        # 3. ARIMA JSON
        if self.arima_json_path.is_file():
            api.upload_file(
                path_or_fileobj=str(self.arima_json_path),
                path_in_repo="arima/arima_Frozen_Seafood.json",
                repo_id=self.repo_id,
                repo_type="model",
                commit_message="Update ARIMA evaluation metrics"
            )
            uploaded.append("arima/arima_Frozen_Seafood.json")

        # 4. Model Card README.md
        metrics_info = ""
        if self.arima_json_path.is_file():
            try:
                m = json.loads(self.arima_json_path.read_text(encoding="utf-8"))
                metrics_info = (
                    f"- **Model Order**: `{m.get('model_order', 'ARIMA(2,0,2)')}`\n"
                    f"- **MAE**: `{m.get('mae', 0):.2f}` boxes\n"
                    f"- **RMSE**: `{m.get('rmse', 0):.2f}` boxes\n"
                    f"- **MAPE**: `{m.get('mape', 0):.2f}%`\n"
                )
            except Exception:
                pass

        card = f"""---
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

Central model repository for **I_LoveSeafood AI Engineering Ecosystem**.

### Models:
1. **YOLO Box Detection (`yolo/yolo11n.pt`)**: Real-time seafood box detection from surveillance camera feeds.
2. **ARIMA Demand Forecasting (`arima/arima_Frozen_Seafood.pkl`)**: Optimal stock inventory prediction.
{metrics_info}
"""
        api.upload_file(
            path_or_fileobj=card.encode("utf-8"),
            path_in_repo="README.md",
            repo_id=self.repo_id,
            repo_type="model",
            commit_message="Update README model card"
        )
        uploaded.append("README.md")

        # Seed MinIO
        self.seed_minio()

        return {
            "status": "success",
            "repo_id": self.repo_id,
            "uploaded_files": uploaded,
            "count": len(uploaded),
            "message": f"Successfully published {len(uploaded)} files to Hugging Face Model Hub ({self.repo_id})."
        }

    def pull_models(self, force: bool = False) -> Dict[str, Any]:
        """ดาวน์โหลดโมเดลจาก Hugging Face Hub ลงเครื่องและ MinIO"""
        from huggingface_hub import hf_hub_download

        self.yolo_path.parent.mkdir(parents=True, exist_ok=True)
        self.arima_pkl_path.parent.mkdir(parents=True, exist_ok=True)

        items = [
            ("yolo/yolo11n.pt", self.yolo_path),
            ("arima/arima_Frozen_Seafood.pkl", self.arima_pkl_path),
            ("arima/arima_Frozen_Seafood.json", self.arima_json_path),
        ]

        downloaded = []
        temp_dir = self.storage_root / "models_temp"

        for hf_name, local_dest in items:
            if local_dest.is_file() and not force:
                continue

            try:
                dl = hf_hub_download(
                    repo_id=self.repo_id,
                    filename=hf_name,
                    token=self.token if self.token else None,
                    local_dir=str(temp_dir)
                )
                shutil.copy2(dl, str(local_dest))
                downloaded.append(hf_name)
            except Exception as e:
                logger.warning(f"Error downloading {hf_name}: {e}")

        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)

        self.seed_minio()

        return {
            "status": "success",
            "repo_id": self.repo_id,
            "downloaded_files": downloaded,
            "count": len(downloaded),
            "message": f"Downloaded {len(downloaded)} files from Hugging Face Hub."
        }

    def seed_minio(self):
        """ซิงค์โมเดลจาก local storage ไปยัง MinIO bucket 'models'"""
        client = self._get_minio_client()
        if not client:
            return

        try:
            if not client.bucket_exists("models"):
                client.make_bucket("models")

            if self.yolo_path.is_file():
                client.fput_object("models", "yolo/base/yolo11n.pt", str(self.yolo_path))

            if self.arima_pkl_path.is_file():
                client.fput_object("models", "arima/Frozen_Seafood/latest/model.pkl", str(self.arima_pkl_path))

            if self.arima_json_path.is_file():
                client.fput_object("models", "arima/Frozen_Seafood/latest/metrics.json", str(self.arima_json_path))
        except Exception as e:
            logger.warning(f"MinIO seed warning: {e}")

    def check_or_pull(self) -> Dict[str, Any]:
        """Hybrid Cache-Aside Check: if files missing, pull from HF"""
        missing = []
        if not self.yolo_path.is_file():
            missing.append("yolo11n.pt")
        if not self.arima_pkl_path.is_file():
            missing.append("arima_Frozen_Seafood.pkl")

        if missing:
            res = self.pull_models(force=False)
            res["cache_status"] = "miss"
            res["missing_before"] = missing
            return res
        else:
            self.seed_minio()
            return {
                "status": "success",
                "cache_status": "hit",
                "message": "All required models are present in local cache and MinIO."
            }


hf_service = HuggingFaceService()
