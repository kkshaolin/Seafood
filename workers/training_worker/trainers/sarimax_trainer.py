"""SARIMAX Trainer module (alias/re-export of arima_trainer.py)."""
from training_worker.trainers.arima_trainer import train_arima_model as train_sarimax_model
from training_worker.trainers.arima_trainer import train_arima_model

__all__ = ["train_sarimax_model", "train_arima_model"]
