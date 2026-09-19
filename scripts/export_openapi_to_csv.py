import csv
import json
import os
import sys
import urllib.request
from pathlib import Path

# Add workspace root and backend directory to Python path
workspace_root = Path(__file__).resolve().parents[1]
backend_path = workspace_root / "backend"
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

import pandas as pd
from backend.src.utils.logger import get_logger

logger = get_logger("openapi_exporter")


def fetch_openapi_schema(url: str = "http://localhost:8000/openapi.json") -> dict:
    """Fetch OpenAPI schema from live server or generate directly from FastAPI app in memory."""
    try:
        logger.info(f"Attempting to fetch OpenAPI schema from live server: {url}")
        req = urllib.request.Request(url, headers={"User-Agent": "FastAPI-Exporter/1.0"})
        with urllib.request.urlopen(req, timeout=3) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                logger.info("Successfully retrieved openapi.json from live FastAPI server.")
                return data
    except Exception as e:
        logger.warning(f"Live server not reachable ({e}). Generating schema directly from FastAPI app in memory...")

    # Direct fallback generation from FastAPI app instance
    try:
        from backend.src.main import app
        schema = app.openapi()
        logger.info("Successfully generated OpenAPI schema directly from FastAPI app instance.")
        return schema
    except Exception as ex:
        logger.error(f"Failed to generate OpenAPI schema: {ex}")
        raise ex


def parse_openapi_to_rows(schema: dict) -> list[dict]:
    """Parse OpenAPI 3.0 schema dictionary into flat structured rows for CSV/Excel export."""
    rows = []
    paths = schema.get("paths", {})
    
    for path, methods in paths.items():
        for method, spec in methods.items():
            if method.lower() not in {"get", "post", "put", "delete", "patch", "options", "head"}:
                continue
            
            tags = ", ".join(spec.get("tags", ["default"]))
            summary = spec.get("summary", "")
            description = spec.get("description", "").strip().replace("\n", " ")
            operation_id = spec.get("operationId", "")
            
            # Extract parameters
            params = []
            for param in spec.get("parameters", []):
                p_name = param.get("name", "")
                p_in = param.get("in", "")
                p_req = "Required" if param.get("required", False) else "Optional"
                params.append(f"{p_name} ({p_in}, {p_req})")
            params_str = "; ".join(params) if params else "-"
            
            # Extract request body indicator
            req_body = "Yes" if "requestBody" in spec else "No"
            
            # Extract response codes
            responses = list(spec.get("responses", {}).keys())
            responses_str = ", ".join(responses) if responses else "-"
            
            # Security / Auth requirement
            security = "Bearer Token Required" if spec.get("security") or ("security" in schema and "get_current_user" in str(spec)) else "Public"
            if "auth" in tags.lower() and method.lower() == "post":
                security = "Public (Auth Endpoint)"

            rows.append({
                "Tag": tags,
                "HTTP Method": method.upper(),
                "Path / Endpoint": path,
                "Summary": summary,
                "Description": description,
                "Auth Required": security,
                "Request Parameters": params_str,
                "Has Request Body": req_body,
                "Response Status Codes": responses_str,
                "Operation ID": operation_id,
            })
            
    return rows


def export_api_snapshot(output_dir: str = "storage") -> tuple[str, str]:
    """Export OpenAPI snapshot to CSV and Excel files."""
    root_dir = Path(__file__).resolve().parents[1]
    output_path = root_dir / output_dir
    output_path.mkdir(parents=True, exist_ok=True)

    schema = fetch_openapi_schema()
    rows = parse_openapi_to_rows(schema)

    csv_file = output_path / "data" / "csv_file" / "api_snapshot.csv"
    excel_file = output_path / "data" / "excel_file" / "api_snapshot.xlsx"
    csv_file.parent.mkdir(parents=True, exist_ok=True)
    excel_file.parent.mkdir(parents=True, exist_ok=True)

    # 1. Export CSV
    if rows:
        fieldnames = list(rows[0].keys())
        with open(csv_file, mode="w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        logger.info(f"Successfully exported API Snapshot to CSV: {csv_file}")

    # 2. Export Excel using pandas
    try:
        df = pd.DataFrame(rows)
        df.to_excel(excel_file, index=False, engine="openpyxl")
        logger.info(f"Successfully exported API Snapshot to Excel: {excel_file}")
    except Exception as e:
        logger.warning(f"Could not export to Excel (.xlsx): {e}")

    # Print clean summary table to console
    print("\n" + "=" * 80)
    print(f"📊 API SNAPSHOT REPORT (Total Endpoints: {len(rows)})")
    print("=" * 80)
    for idx, r in enumerate(rows, 1):
        print(f"{idx:02d}. [{r['HTTP Method']}] {r['Path / Endpoint']:<30} | Tag: {r['Tag']:<10} | Auth: {r['Auth Required']}")
    print("=" * 80)
    print(f"📁 CSV File  : {csv_file.resolve()}")
    print(f"📁 Excel File: {excel_file.resolve()}")
    print("=" * 80 + "\n")

    return str(csv_file), str(excel_file)


if __name__ == "__main__":
    export_api_snapshot()
