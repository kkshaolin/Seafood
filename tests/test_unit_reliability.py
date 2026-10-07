"""Targeted Unit Tests for Phase 5 Reliability:
- ARQ job status & error handling (never return success-shaped result on failure)
- Schema input validations (invalid input rejection)
- Metric missing & zero-handling (never report uncalculated metrics as 0.0)
- Graceful error handling for missing models/datasets and external service failure
"""
# ruff: noqa: E402
import json
import sys
from pathlib import Path

workspace_root = Path(__file__).resolve().parents[1]
backend_src = workspace_root / "backend" / "src"
workers_dir = workspace_root / "workers"

for p in [str(backend_src), str(workers_dir), str(workspace_root)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import ValidationError

from forecasting.schemas import (
    ForecastRequest, YoloTrainRequest, ForecastMetrics
)
from inference_worker.forecast_model.metrics import (
    calculate_mae, calculate_rmse, calculate_mape,
    evaluate_forecast_against_baselines
)
from forecasting.router import get_forecast_job_status
from arq.jobs import JobStatus


# ---------------------------------------------------------------------------
# 1. Invalid Input Validation Tests
# ---------------------------------------------------------------------------

def test_forecast_request_valid():
    """Valid forecast request passes validation."""
    req = ForecastRequest(product="Frozen Shrimp", p=2, d=0, q=2, forecast_horizon=6)
    assert req.product == "Frozen Shrimp"
    assert req.forecast_horizon == 6


def test_forecast_request_invalid_empty_product():
    """Empty product string must fail validation."""
    with pytest.raises(ValidationError) as exc:
        ForecastRequest(product="")
    assert "product" in str(exc.value)


def test_forecast_request_invalid_negative_horizon():
    """Negative or zero forecast_horizon must fail validation."""
    with pytest.raises(ValidationError):
        ForecastRequest(product="Frozen Shrimp", forecast_horizon=0)
    with pytest.raises(ValidationError):
        ForecastRequest(product="Frozen Shrimp", forecast_horizon=-5)


def test_forecast_request_invalid_order_parameters():
    """Negative ARIMA orders must fail validation."""
    with pytest.raises(ValidationError):
        ForecastRequest(product="Frozen Shrimp", p=-1)
    with pytest.raises(ValidationError):
        ForecastRequest(product="Frozen Shrimp", d=-1)
    with pytest.raises(ValidationError):
        ForecastRequest(product="Frozen Shrimp", q=-1)


def test_yolo_train_request_valid():
    """Valid YOLO train request passes validation."""
    req = YoloTrainRequest(dataset_name="box_v1", epochs=20, imgsz=640, batch=8, patience=5)
    assert req.dataset_name == "box_v1"
    assert req.epochs == 20


def test_yolo_train_request_invalid_epochs():
    """Zero or negative epochs must fail validation."""
    with pytest.raises(ValidationError):
        YoloTrainRequest(dataset_name="box_v1", epochs=0)
    with pytest.raises(ValidationError):
        YoloTrainRequest(dataset_name="box_v1", epochs=-10)


def test_yolo_train_request_invalid_batch():
    """Invalid batch size must fail validation."""
    with pytest.raises(ValidationError):
        YoloTrainRequest(dataset_name="box_v1", batch=0)


# ---------------------------------------------------------------------------
# 2. Metric Missing & Honest Reporting Tests
# ---------------------------------------------------------------------------

def test_metrics_defaults_to_none_not_zero():
    """ForecastMetrics must default uncalculated values to None, not 0.0."""
    metrics = ForecastMetrics()
    assert metrics.mae is None
    assert metrics.rmse is None
    assert metrics.mape is None
    assert metrics.aic is None
    assert metrics.bic is None


def test_calculate_mae_missing_or_empty():
    """calculate_mae returns None on empty or mismatched inputs."""
    assert calculate_mae([], []) is None
    assert calculate_mae([1, 2], [1]) is None


def test_calculate_rmse_missing_or_empty():
    """calculate_rmse returns None on empty or mismatched inputs."""
    assert calculate_rmse([], []) is None
    assert calculate_rmse([1, 2], [1]) is None


def test_calculate_mape_zero_actuals_returns_none():
    """calculate_mape returns None when actuals are all zero to avoid division by zero."""
    assert calculate_mape([0, 0, 0], [1, 2, 3]) is None
    assert calculate_mape([], []) is None


def test_evaluate_against_baselines_with_valid_and_zero_data():
    """evaluate_forecast_against_baselines calculates metrics honestly without spoofing 0.0."""
    import numpy as np
    y_train = np.array([10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32, 34, 36])
    y_true = np.array([38, 40])
    y_pred = np.array([37, 41])

    res = evaluate_forecast_against_baselines(y_train, y_true, y_pred, season_length=12)
    assert res["eval_status"] == "evaluated"
    assert res["mae"] is not None
    assert res["rmse"] is not None
    assert res["mape"] is not None
    assert res["baselines"]["naive"]["mae"] is not None
    assert res["baselines"]["seasonal_naive"]["mae"] is not None


# ---------------------------------------------------------------------------
# 3. ARQ Job Status & Error Handling (Worker Failure / Success-Shaped Result Prevention)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_job_status_worker_exception():
    """When worker raises unhandled exception, API must return status='failed' with error, result=None."""
    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(return_value=None)

    with patch("forecasting.router.Job") as MockJob:
        mock_job = MagicMock()
        mock_job.status = AsyncMock(return_value=JobStatus.complete)
        
        # Simulate worker crashed with an exception: info.success = False, info.result = RuntimeError
        mock_result_info = MagicMock()
        mock_result_info.success = False
        mock_result_info.result = RuntimeError("Worker out of memory (OOM)")
        mock_job.result_info = AsyncMock(return_value=mock_result_info)

        MockJob.return_value = mock_job

        resp = await get_forecast_job_status("job-failed-123", redis=mock_redis)

        assert resp.status == "failed"
        assert resp.result is None, "Failed job must NOT return success-shaped result"
        assert "Worker out of memory (OOM)" in resp.error


@pytest.mark.asyncio
async def test_get_job_status_worker_error_dict():
    """When worker returns an error dictionary, API must return status='failed' with error, result=None."""
    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(return_value=None)

    with patch("forecasting.router.Job") as MockJob:
        mock_job = MagicMock()
        mock_job.status = AsyncMock(return_value=JobStatus.complete)

        # Worker handled error internally and returned status='error'
        mock_result_info = MagicMock()
        mock_result_info.success = True
        mock_result_info.result = {
            "status": "error",
            "error": "Dataset 'nonexistent_ds' not found in MinIO bucket 'datasets'"
        }
        mock_job.result_info = AsyncMock(return_value=mock_result_info)

        MockJob.return_value = mock_job

        resp = await get_forecast_job_status("job-ds-not-found", redis=mock_redis)

        assert resp.status == "failed"
        assert resp.result is None, "Failed job must NOT return a success-shaped result"
        assert "not found in MinIO" in resp.error


@pytest.mark.asyncio
async def test_get_job_status_success():
    """When worker succeeds, API returns status='completed' with valid result."""
    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(return_value=None)

    with patch("forecasting.router.Job") as MockJob:
        mock_job = MagicMock()
        mock_job.status = AsyncMock(return_value=JobStatus.complete)

        mock_result_info = MagicMock()
        mock_result_info.success = True
        mock_result_info.result = {
            "status": "success",
            "model_type": "arima",
            "product": "Frozen Shrimp",
            "job_id": "job-success-123",
            "metrics": {"mae": 5.76, "rmse": 8.00, "mape": 10.73}
        }
        mock_job.result_info = AsyncMock(return_value=mock_result_info)

        MockJob.return_value = mock_job

        resp = await get_forecast_job_status("job-success-123", redis=mock_redis)

        assert resp.status == "completed"
        assert resp.error is None
        assert resp.result is not None
        assert resp.result.status == "success"
        assert resp.result.metrics["mae"] == 5.76


@pytest.mark.asyncio
async def test_get_job_status_running():
    """When worker is in progress, API returns status='running', result=None."""
    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(return_value=None)

    with patch("forecasting.router.Job") as MockJob:
        mock_job = MagicMock()
        mock_job.status = AsyncMock(return_value=JobStatus.in_progress)
        mock_job.result_info = AsyncMock(return_value=None)

        MockJob.return_value = mock_job

        resp = await get_forecast_job_status("job-running-123", redis=mock_redis)

        assert resp.status == "running"
        assert resp.result is None
        assert resp.error is None


@pytest.mark.asyncio
async def test_get_job_status_includes_sampling_progress():
    """Running forecast jobs expose newly sampled frames before forecasting completes."""
    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(return_value=json.dumps({
        "sampled_frames": {
            "cam_main": "ZoneA/frame_20261007_091234_123456.jpg",
            "cam_dock": "ZoneB/frame_20261007_091234_123456.jpg",
        },
        "sampled_detections": {"cam_main": 4, "cam_dock": 3},
    }))

    with patch("forecasting.router.Job") as MockJob:
        mock_job = MagicMock()
        mock_job.status = AsyncMock(return_value=JobStatus.in_progress)
        mock_job.result_info = AsyncMock(return_value=None)
        MockJob.return_value = mock_job

        resp = await get_forecast_job_status("job-running-sampling-123", redis=mock_redis)

    assert resp.status == "running"
    assert resp.sampled_frames["cam_main"].startswith("ZoneA/frame_")
    assert resp.sampled_detections == {"cam_main": 4, "cam_dock": 3}


# ---------------------------------------------------------------------------
# 4. Missing Dataset & Model Handling Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_forecasting_service_missing_product_data():
    """ForecastingService raises PreprocessingError when no stock records exist for product."""
    from inference_worker.forecast_model.service import ForecastingService
    from inference_worker.forecast_model.preprocessing import PreprocessingError
    import pandas as pd

    mock_session = AsyncMock()
    service = ForecastingService(mock_session)

    # Mock get_inventory_data to return empty dataframe
    service.get_inventory_data = AsyncMock(return_value=pd.DataFrame())

    req = ForecastRequest(product="NonExistent_Shrimp_9999", forecast_horizon=3)
    with pytest.raises(PreprocessingError) as exc_info:
        await service.run_forecast(req)

    assert "Insufficient data" in str(exc_info.value)
    assert "NonExistent_Shrimp_9999" in str(exc_info.value)


@pytest.mark.asyncio
async def test_yolo_trainer_missing_dataset_in_minio():
    """YOLO trainer returns status='error' with clear message when dataset is not found in MinIO."""
    from training_worker.worker import run_training_task

    mock_ctx = {"job_id": "job-missing-ds-456"}
    req_data = {
        "model_type": "yolo",
        "dataset_name": "definitely_nonexistent_dataset_12345",
        "epochs": 1
    }

    mock_minio = MagicMock()
    mock_minio.stat_object.side_effect = Exception("Object not found in MinIO")

    with patch("training_worker.trainers.yolo_trainer._get_minio_client", return_value=mock_minio):
        result = await run_training_task(mock_ctx, req_data)

    assert isinstance(result, dict)
    assert result.get("status") == "error"
    assert "error" in result
    assert result.get("job_id") == "job-missing-ds-456"
    assert result.get("model_type") == "yolo"


# ---------------------------------------------------------------------------
# 5. MLflow / MinIO Unavailable Resilience Tests
# ---------------------------------------------------------------------------

def test_minio_upload_bytes_error_handling():
    """_upload_bytes raises exception when MinIO is unreachable so caller knows it failed."""
    from training_worker.trainers.arima_trainer import _upload_bytes

    mock_client = MagicMock()
    mock_client.bucket_exists.side_effect = Exception("MinIO connection refused at minio:9000")

    with pytest.raises(Exception) as exc:
        _upload_bytes(mock_client, "models", "test_key", b"test_data")

    assert "MinIO connection refused" in str(exc.value)


@pytest.mark.asyncio
async def test_arima_trainer_handles_mlflow_unavailable_gracefully():
    """ARIMA trainer continues and logs warning if MLflow tracking server is down."""
    from training_worker.trainers.arima_trainer import train_arima_model
    import pandas as pd
    import numpy as np

    # Generate 36 months of mock series
    dates = pd.date_range("2021-01-01", periods=36, freq="MS")
    quantities = 50.0 + np.sin(np.linspace(0, 10, 36)) * 10
    mock_df = pd.DataFrame({"recorded_at": dates, "quantity": quantities})

    with patch("training_worker.trainers.arima_trainer._fetch_inventory_summaries", AsyncMock(return_value=mock_df)), \
         patch("training_worker.trainers.arima_trainer._fetch_camera_exog", AsyncMock(return_value=pd.DataFrame())), \
         patch("training_worker.trainers.arima_trainer._get_minio_client") as MockMinio, \
         patch("mlflow.set_experiment", side_effect=Exception("MLflow tracking server connection failed")):

        mock_minio = MagicMock()
        mock_minio.bucket_exists.return_value = True
        MockMinio.return_value = mock_minio

        # Should complete training and return valid result despite MLflow being down
        res = await train_arima_model(
            job_id="test-job-mlflow-down",
            product="Frozen Shrimp",
            p=1, d=0, q=1,
            forecast_horizon=3,
            auto_order=False
        )

        assert res["status"] == "success"
        assert res["product"] == "Frozen Shrimp"
        assert res["mlflow_run_id"] is None, "MLflow run ID should be None when MLflow is unreachable"
        assert res["metrics"]["mae"] is not None
