"""
Training Worker - โหลด dataset จาก MinIO, เทรนโมเดล, บันทึกผล
"""
import os
import json
import logging
from datetime import datetime
from pathlib import Path
from minio import Minio
from minio.error import S3Error
from datasets import load_dataset, load_from_disk
import torch
import mlflow
from transformers import (
    AutoTokenizer,
    AutoModelForTokenClassification,
    TrainingArguments,
    Trainer,
    DataCollatorForTokenClassification
)

# MLflow Tracking Configuration
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)

# ตั้งค่า logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# MinIO configuration
MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT', 'minio:9000')
MINIO_ACCESS_KEY = os.getenv('MINIO_ACCESS_KEY', 'minioadmin')
MINIO_SECRET_KEY = os.getenv('MINIO_SECRET_KEY', 'minioadmin')
BUCKET_NAME = "training-data"

# Storage paths
STORAGE_BASE = Path("/app/storage")
DATA_DIR = STORAGE_BASE / "data"
LOGS_DIR = STORAGE_BASE / "logs"
MODELS_DIR = STORAGE_BASE / "models"

# สร้าง directories
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)


def get_minio_client() -> Minio:
    """สร้าง MinIO client"""
    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False
    )


def ensure_bucket_exists(client: Minio):
    """สร้าง bucket ถ้ายังไม่มี"""
    for bucket in [BUCKET_NAME, "mlflow-artifacts"]:
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
            logger.info(f"Created bucket: {bucket}")


def download_dataset_from_minio(client: Minio, dataset_name: str) -> Path:
    """ดาวน์โหลด dataset จาก MinIO"""
    safe_name = dataset_name.replace('/', '_')
    local_path = DATA_DIR / safe_name
    local_path.mkdir(parents=True, exist_ok=True)
    
    prefix = f"datasets/{safe_name}/"
    
    try:
        objects = client.list_objects(BUCKET_NAME, prefix=prefix, recursive=True)
        for obj in objects:
            local_file = local_path / Path(obj.object_name).name
            client.fget_object(BUCKET_NAME, obj.object_name, str(local_file))
            logger.info(f"Downloaded: {obj.object_name}")
        
        return local_path
    except S3Error as e:
        logger.error(f"Error downloading dataset: {e}")
        raise


def upload_to_minio(client: Minio, local_path: Path, prefix: str):
    """อัปโหลดไฟล์/โฟลเดอร์ขึ้น MinIO"""
    if local_path.is_file():
        object_name = f"{prefix}/{local_path.name}"
        client.fput_object(BUCKET_NAME, object_name, str(local_path))
        logger.info(f"Uploaded: {object_name}")
    elif local_path.is_dir():
        for file_path in local_path.rglob('*'):
            if file_path.is_file():
                relative = file_path.relative_to(local_path)
                object_name = f"{prefix}/{relative}"
                client.fput_object(BUCKET_NAME, object_name, str(file_path))
                logger.info(f"Uploaded: {object_name}")


async def train_model(ctx, job_data: dict):
    """
    ARQ Job Function: เทรนโมเดล Token Classification
    
    Args:
        ctx: ARQ context (มี redis, job_id, etc.)
        job_data: dict containing job parameters
    """
    job_id = job_data.get('job_id')
    dataset_name = job_data.get('dataset_name')
    model_name = job_data.get('model_name', 'distilbert-base-uncased')
    epochs = job_data.get('epochs', 3)
    batch_size = job_data.get('batch_size', 16)
    
    # ตั้งค่า log file สำหรับ job นี้
    log_file = LOGS_DIR / f"{job_id}.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    ))
    logger.addHandler(file_handler)
    
    logger.info(f"=== Starting Training Job {job_id} ===")
    logger.info(f"Dataset: {dataset_name}")
    logger.info(f"Model: {model_name}")
    logger.info(f"Epochs: {epochs}, Batch Size: {batch_size}")
    logger.info(f"GPU Available: {torch.cuda.is_available()}")
    
    try:
        # Step 1: เชื่อมต่อ MinIO
        minio_client = get_minio_client()
        ensure_bucket_exists(minio_client)
        
        # Step 2: โหลด Dataset
        safe_name = dataset_name.replace('/', '_')
        local_dataset_path = DATA_DIR / safe_name
        
        if local_dataset_path.exists() and (local_dataset_path / "dataset_dict.json").exists():
            logger.info("Loading dataset from local cache...")
            dataset = load_from_disk(str(local_dataset_path))
        else:
            # ลองโหลดจาก MinIO ก่อน
            try:
                logger.info("Downloading dataset from MinIO...")
                download_dataset_from_minio(minio_client, dataset_name)
                dataset = load_from_disk(str(local_dataset_path))
            except Exception:
                # ถ้าไม่มีใน MinIO ให้โหลดจาก Hugging Face
                logger.info(f"Loading dataset '{dataset_name}' from Hugging Face...")
                dataset = load_dataset(dataset_name, trust_remote_code=True)
                
                # บันทึกลง MinIO
                logger.info("Saving dataset to MinIO...")
                dataset.save_to_disk(str(local_dataset_path))
                upload_to_minio(minio_client, local_dataset_path, f"datasets/{safe_name}")
        
        logger.info(f"Dataset loaded: {dataset}")
        
        # Step 3: โหลด Tokenizer และ Model
        logger.info("Loading tokenizer and model...")
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        
        # สำหรับ CoNLL-2003 มี 9 labels
        num_labels = 9
        model = AutoModelForTokenClassification.from_pretrained(
            model_name,
            num_labels=num_labels,
            ignore_mismatched_sizes=True
        )
        
        # Step 4: Preprocessing
        def tokenize_and_align_labels(examples):
            tokenized_inputs = tokenizer(
                examples["tokens"],
                truncation=True,
                is_split_into_words=True,
                max_length=128
            )
            
            labels = []
            for i, label in enumerate(examples["ner_tags"]):
                word_ids = tokenized_inputs.word_ids(batch_index=i)
                previous_word_idx = None
                label_ids = []
                
                for word_idx in word_ids:
                    if word_idx is None:
                        label_ids.append(-100)
                    elif word_idx != previous_word_idx:
                        label_ids.append(label[word_idx])
                    else:
                        label_ids.append(-100)
                    previous_word_idx = word_idx
                
                labels.append(label_ids)
            
            tokenized_inputs["labels"] = labels
            return tokenized_inputs
        
        logger.info("Tokenizing dataset...")
        tokenized_dataset = dataset.map(
            tokenize_and_align_labels,
            batched=True,
            remove_columns=dataset["train"].column_names
        )
        
        # Step 5: Training Arguments
        output_dir = MODELS_DIR / job_id
        output_dir.mkdir(parents=True, exist_ok=True)
        
        eval_dataset = None
        if "validation" in tokenized_dataset:
            eval_dataset = tokenized_dataset["validation"]
        elif "test" in tokenized_dataset:
            eval_dataset = tokenized_dataset["test"]

        training_args = TrainingArguments(
            output_dir=str(output_dir),
            num_train_epochs=epochs,
            per_device_train_batch_size=batch_size,
            warmup_steps=500,
            weight_decay=0.01,
            logging_dir=str(output_dir / "logs"),
            logging_steps=10,
            save_strategy="epoch",
            evaluation_strategy="epoch" if eval_dataset else "no",
            report_to="none",
            max_steps=10,  # เร่งให้เทรนเสร็จไวเพื่อดูผลลัพธ์
            fp16=False,
            use_cpu=False,  # ใช้ GPU ตามที่โจทย์ต้องการ
        )
        
        data_collator = DataCollatorForTokenClassification(tokenizer)
        
        # Step 6: Train
        logger.info("Starting training...")
        mlflow.set_experiment(dataset_name)
        with mlflow.start_run(run_name=job_id) as run:
            run_id = run.info.run_id
            mlflow.log_params({
                "model_name": model_name,
                "epochs": epochs,
                "batch_size": batch_size,
                "dataset_name": dataset_name
            })
            
            trainer = Trainer(
                model=model,
                args=training_args,
                train_dataset=tokenized_dataset["train"],
                eval_dataset=eval_dataset,
                tokenizer=tokenizer,
                data_collator=data_collator,
            )
            
            from transformers.integrations import MLflowCallback
            if trainer.pop_callback(MLflowCallback) is not None:
                pass
            train_result = trainer.train()
            mlflow.log_metric("train_loss", train_result.training_loss)
            
            if eval_dataset:
                logger.info("Evaluating model...")
                eval_result = trainer.evaluate()
                for key, value in eval_result.items():
                    mlflow.log_metric(f"eval_{key}" if not key.startswith("eval_") else key, value)
            
            # Step 7: Save Model
            logger.info("Saving model...")
            final_model_dir = output_dir / "final_model"
            final_model_dir.mkdir(exist_ok=True)
            trainer.save_model(str(final_model_dir))
            tokenizer.save_pretrained(str(final_model_dir))
            
            # Use custom pyfunc model to bypass mlflow.transformers bugs with task inference
            class TokenClassificationPyFunc(mlflow.pyfunc.PythonModel):
                def load_context(self, context):
                    from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline
                    self.tokenizer = AutoTokenizer.from_pretrained(context.artifacts["model_path"])
                    self.model = AutoModelForTokenClassification.from_pretrained(context.artifacts["model_path"])
                    self.pipeline = pipeline("token-classification", model=self.model, tokenizer=self.tokenizer)

                def predict(self, context, model_input):
                    if hasattr(model_input, "tolist"):
                        model_input = model_input.tolist()
                    if isinstance(model_input, dict) and "inputs" in model_input:
                        model_input = model_input["inputs"]
                    
                    preds = self.pipeline(model_input)
                    
                    # Convert numpy types to native Python types for JSON serialization
                    if isinstance(preds, list):
                        for res in preds:
                            if isinstance(res, list):
                                for r in res:
                                    for k, v in r.items():
                                        if hasattr(v, "item"): r[k] = v.item()
                            elif isinstance(res, dict):
                                for k, v in res.items():
                                    if hasattr(v, "item"): res[k] = v.item()
                    return preds

            mlflow.pyfunc.log_model(
                artifact_path="model",
                python_model=TokenClassificationPyFunc(),
                artifacts={"model_path": str(final_model_dir)}
            )
            
            # Create Model URI for inference
            model_uri = f"runs:/{run_id}/model"
            logger.info(f"MLflow Model URI: {model_uri}")
            
            # Step 8: Upload Model to MinIO (Legacy direct upload, MLflow also uploads to MinIO via artifact store)
            logger.info("Uploading model to MinIO...")
            upload_to_minio(minio_client, output_dir, f"models/{job_id}")
            
            # Step 9: Upload Log to MinIO
            logger.info("Uploading log to MinIO...")
            upload_to_minio(minio_client, log_file, f"logs")
            
            logger.info(f"=== Training Job {job_id} Completed Successfully ===")
            
            # ลบ file handler
            logger.removeHandler(file_handler)
            file_handler.close()
        
        return {
            "status": "success",
            "job_id": job_id,
            "model_path": f"models/{job_id}",
            "model_uri": model_uri,
            "log_path": f"logs/{job_id}.log",
            "train_loss": train_result.training_loss,
            "epochs": epochs
        }
        
    except Exception as e:
        logger.error(f"Training failed: {str(e)}", exc_info=True)
        
        # Upload error log
        if log_file.exists():
            upload_to_minio(minio_client, log_file, f"logs")
        
        logger.removeHandler(file_handler)
        file_handler.close()
        
        return {
            "status": "failed",
            "job_id": job_id,
            "error": str(e)
        }

from arq.connections import RedisSettings

class WorkerSettings:
    functions = [train_model]
    queue_name = "training_queue"
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://redis:6379"))
    max_jobs = 1
    poll_delay = 0.5