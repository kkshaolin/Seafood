"""Integration tests for ShrimpStock AI pipeline:
API (FastAPI) -> Queue (Redis/ARQ) -> Worker (forecasting/sampling) -> Model (YOLO/ARIMA) -> DB/MinIO.

Runs non-destructively against local Docker environment (localhost:8000).
"""
import time
import urllib.request
import urllib.error
import json
import pytest

BASE_URL = "http://localhost:8000"


def _http_get(endpoint: str, timeout: int = 15):
    req = urllib.request.Request(f"{BASE_URL}{endpoint}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.getcode(), resp.headers.get_content_type(), resp.read()


def _http_post_json(endpoint: str, payload: dict, timeout: int = 15):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}{endpoint}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.getcode(), json.loads(resp.read().decode("utf-8"))


def test_health_check():
    """Verify backend health check reports connected for DB, Redis, and MinIO."""
    code, ctype, body = _http_get("/health")
    assert code == 200, f"Expected 200, got {code}"
    data = json.loads(body.decode("utf-8"))
    assert data.get("status") == "healthy", f"Status degraded: {data}"
    services = data.get("services", {})
    assert services.get("database") == "connected", f"Database not connected: {services}"
    assert services.get("redis") == "connected", f"Redis not connected: {services}"
    assert services.get("minio") == "connected", f"MinIO not connected: {services}"


def test_stock_summary_and_history():
    """Verify stock summary and historical inventory endpoints."""
    code, _, body = _http_get("/api/stock/summary")
    assert code == 200
    summary = json.loads(body.decode("utf-8"))
    assert "current_stock" in summary or "total_boxes" in summary or "products" in summary

    code, _, body = _http_get("/api/stock/history?product=Frozen_Seafood")
    assert code == 200
    hist = json.loads(body.decode("utf-8"))
    assert "data" in hist
    assert len(hist["data"]) > 0, "Expected non-empty monthly history data"


def test_camera_endpoints():
    """Verify camera frame snapshot and latest detection metadata."""
    code, _, body = _http_get("/api/camera/cam_main/latest")
    assert code == 200
    meta = json.loads(body.decode("utf-8"))
    assert meta.get("camera_id") == "cam_main"
    assert "status" in meta

    code, ctype, frame_bytes = _http_get("/api/camera/cam_main/frame")
    assert code == 200
    assert ctype == "image/jpeg"
    assert len(frame_bytes) > 1000, "Frame JPEG bytes too small or empty"


def test_end_to_end_forecast_pipeline():
    """Verify end-to-end flow: POST /api/forecast -> queue -> worker -> DB/MinIO."""
    payload = {
        "product": "Frozen_Seafood",
        "forecast_horizon": 3,
        "p": 2,
        "d": 0,
        "q": 2
    }
    code, res = _http_post_json("/api/forecast", payload)
    assert code == 202, f"Expected 202 Accepted, got {code}"
    job_id = res.get("job_id")
    assert job_id, "Missing job_id in forecast enqueue response"

    # Poll job status until completed (up to 45 seconds)
    max_wait = 45
    start = time.time()
    completed = False
    last_status = None

    while time.time() - start < max_wait:
        time.sleep(2)
        code, _, status_res = _http_get(f"/api/forecast/{job_id}")
        assert code == 200
        data = json.loads(status_res.decode("utf-8"))
        last_status = data.get("status")
        if last_status == "completed":
            completed = True
            result = data.get("result", {})
            assert "forecast" in result, f"Expected 'forecast' in result: {result}"
            forecast_points = result["forecast"]
            assert len(forecast_points) == 3, f"Expected 3 forecast points, got {len(forecast_points)}"
            break
        elif last_status == "failed":
            pytest.fail(f"Forecast job failed: {data.get('error')}")

    assert completed, f"Job {job_id} did not complete within {max_wait}s (last status: {last_status})"


def test_invalid_inputs_rejected_by_api():
    """Verify backend rejects invalid forecast/training payloads with HTTP 422."""
    # 1. Empty product string
    try:
        _http_post_json("/api/forecast", {"product": "", "forecast_horizon": 3})
        pytest.fail("Expected 422 for empty product string")
    except urllib.error.HTTPError as err:
        assert err.code == 422, f"Expected 422, got {err.code}"

    # 2. Negative horizon
    try:
        _http_post_json("/api/forecast", {"product": "Frozen_Seafood", "forecast_horizon": -3})
        pytest.fail("Expected 422 for negative horizon")
    except urllib.error.HTTPError as err:
        assert err.code == 422, f"Expected 422, got {err.code}"

    # 3. Invalid YOLO epochs (zero epochs)
    try:
        _http_post_json("/api/forecast/train/yolo", {"dataset_name": "box_v1", "epochs": 0})
        pytest.fail("Expected 422 for zero epochs")
    except urllib.error.HTTPError as err:
        assert err.code == 422, f"Expected 422, got {err.code}"


def test_job_status_not_found():
    """Verify polling nonexistent job returns HTTP 404."""
    try:
        _http_get("/api/forecast/nonexistent-uuid-00000000")
        pytest.fail("Expected 404 for unknown job ID")
    except urllib.error.HTTPError as err:
        assert err.code == 404, f"Expected 404, got {err.code}"


def test_forecast_missing_product_fails_cleanly():
    """Verify forecasting for a nonexistent product results in status='failed' without success result."""
    payload = {
        "product": "Unknown_Species_NonExistent_9999",
        "forecast_horizon": 3,
        "p": 1,
        "d": 0,
        "q": 1
    }
    code, res = _http_post_json("/api/forecast", payload)
    assert code == 202
    job_id = res.get("job_id")
    assert job_id

    # Poll status - should fail cleanly
    max_wait = 30
    start = time.time()
    done = False

    while time.time() - start < max_wait:
        time.sleep(2)
        code, _, status_res = _http_get(f"/api/forecast/{job_id}")
        assert code == 200
        data = json.loads(status_res.decode("utf-8"))
        if data.get("status") == "failed":
            done = True
            assert data.get("result") is None, "Failed job must NOT return success-shaped result"
            assert "Insufficient data" in data.get("error", "") or "No stock records found" in data.get("error", "")
            break
        elif data.get("status") == "completed":
            pytest.fail("Job for nonexistent product should not complete successfully")

    assert done, f"Job did not fail within {max_wait}s"


if __name__ == "__main__":
    print("Running integration tests...")
    test_health_check()
    print("[PASS] test_health_check")
    test_stock_summary_and_history()
    print("[PASS] test_stock_summary_and_history")
    test_camera_endpoints()
    print("[PASS] test_camera_endpoints")
    test_invalid_inputs_rejected_by_api()
    print("[PASS] test_invalid_inputs_rejected_by_api")
    test_job_status_not_found()
    print("[PASS] test_job_status_not_found")
    test_forecast_missing_product_fails_cleanly()
    print("[PASS] test_forecast_missing_product_fails_cleanly")
    test_end_to_end_forecast_pipeline()
    print("[PASS] test_end_to_end_forecast_pipeline")
    print("\nALL INTEGRATION TESTS PASSED SUCCESSFULLY!")
