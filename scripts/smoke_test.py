#!/usr/bin/env python3
"""Production Smoke Test Suite for I_LoveSeafood AI Ecosystem.

Verifies end-to-end operational readiness across all services:
1. Frontend Web Service (Production Nginx Static Build / SPA)
2. Public application API endpoints through the frontend reverse proxy
3. Optional private backend liveness/readiness probes when --backend-url is reachable

Usage:
    python scripts/smoke_test.py --frontend-url https://stock.example.com
    python scripts/smoke_test.py --frontend-url http://localhost:8081 --backend-url http://localhost:8000
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Dict, Tuple


def check_url(url: str, timeout: int = 5, expected_codes: Tuple[int, ...] = (200,)) -> Tuple[bool, int, str]:
    """Perform HTTP GET request and return success status, code, and response time/message."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "SmokeTest/1.0", "Accept": "*/*"}
        )
        start_t = time.time()
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed = (time.time() - start_t) * 1000
            code = resp.getcode()
            is_ok = code in expected_codes
            return is_ok, code, f"OK ({elapsed:.1f}ms)"
    except urllib.error.HTTPError as e:
        is_ok = e.code in expected_codes
        return is_ok, e.code, f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return False, 0, f"URLError: {e.reason}"
    except Exception as e:
        return False, 0, f"Exception: {type(e).__name__} {e}"


def check_backend_readiness(backend_url: str) -> Tuple[bool, str]:
    """Verify backend /health/ready endpoint reports DB, Redis, and MinIO as connected."""
    url = f"{backend_url.rstrip('/')}/health/ready"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        start_t = time.time()
        with urllib.request.urlopen(req, timeout=8) as resp:
            elapsed = (time.time() - start_t) * 1000
            if resp.getcode() != 200:
                return False, f"HTTP {resp.getcode()}"
            data = json.loads(resp.read().decode())
            status = data.get("status")
            services = data.get("services", {})
            db = services.get("database")
            redis = services.get("redis")
            minio = services.get("minio")

            if status == "healthy" and db == "connected" and redis == "connected" and minio == "connected":
                return True, f"DB: {db}, Redis: {redis}, MinIO: {minio} ({elapsed:.1f}ms)"
            else:
                return False, f"Degraded status={status}: DB={db}, Redis={redis}, MinIO={minio}"
    except Exception as e:
        return False, f"Failed: {e}"


def run_smoke_tests(frontend_url: str, backend_url: str | None = None) -> bool:
    print("=" * 75)
    print("      I_LoveSeafood AI Ecosystem - Production Smoke Test Suite")
    print("=" * 75)
    print(f"Target Frontend UI: {frontend_url}")
    if backend_url:
        print(f"Private Backend API: {backend_url}")
    print("-" * 75)

    results: Dict[str, Tuple[bool, str]] = {}

    # 1. Frontend SPA Service (Nginx / Vite)
    fe_ok, code, msg = check_url(frontend_url)
    results["Frontend Web Service (SPA)"] = (fe_ok, f"Status: {code} [{msg}]")

    api_base = f"{frontend_url.rstrip('/')}/api"

    # 2. Public application API through the frontend's internal Nginx proxy
    stock_sum_ok, code, msg = check_url(f"{api_base}/stock/summary")
    results["Stock Summary API (/api/stock/summary)"] = (stock_sum_ok, f"Status: {code} [{msg}]")

    stock_prod_ok, code, msg = check_url(f"{api_base}/stock/products")
    results["Stock Products API (/api/stock/products)"] = (stock_prod_ok, f"Status: {code} [{msg}]")

    forecast_ok, code, msg = check_url(f"{api_base}/forecast/latest?product=Frozen%20Shrimp")
    results["ARIMA Forecast Endpoint (/api/forecast/latest)"] = (forecast_ok, f"Status: {code} [{msg}]")

    sampling_ok, code, msg = check_url(f"{api_base}/sampling/status")
    results["Camera Sampling Status (/api/sampling/status)"] = (sampling_ok, f"Status: {code} [{msg}]")

    hf_ok, code, msg = check_url(f"{api_base}/hf/status")
    results["Model & HF Cache Status (/api/hf/status)"] = (hf_ok, f"Status: {code} [{msg}]")

    # 3. Private backend probes are optional because production does not publish backend ports.
    if backend_url:
        private_url = backend_url.rstrip("/")
        live_ok, code, msg = check_url(f"{private_url}/health/live")
        results["Private Backend Liveness (/health/live)"] = (live_ok, f"Status: {code} [{msg}]")
        ready_ok, ready_msg = check_backend_readiness(private_url)
        results["Private Backend Readiness (/health/ready)"] = (ready_ok, ready_msg)
        health_ok, code, msg = check_url(f"{private_url}/health")
        results["Private Backend Health (/health)"] = (health_ok, f"Status: {code} [{msg}]")

    # Output Report
    all_passed = True
    print("\n--- Smoke Test Checklist Results ---")
    for name, (passed, details) in results.items():
        tag = "[ PASS ]" if passed else "[ FAIL ]"
        if not passed:
            all_passed = False
        print(f" {tag} {name.ljust(48)} : {details}")

    print("-" * 75)
    if all_passed:
        print(f">>> ALL SMOKE TESTS PASSED ({len(results)}/{len(results)})! The ecosystem is ready. <<<")
    else:
        print(">>> WARNING: One or more smoke tests failed. Please review logs. <<<")
    print("=" * 75)
    return all_passed


def main():
    parser = argparse.ArgumentParser(description="Run Production Smoke Tests")
    parser.add_argument("--backend-url", help="Optional private backend URL for liveness/readiness probes")
    parser.add_argument("--frontend-url", default="http://localhost:8081", help="Frontend SPA base URL")
    args = parser.parse_args()

    success = run_smoke_tests(
        frontend_url=args.frontend_url,
        backend_url=args.backend_url,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
