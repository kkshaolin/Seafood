import csv
import json
import os
import sys
import urllib.request
from pathlib import Path

# เพิ่ม root และ backend ลง Python path เพื่อให้สคริปต์ import แอปได้เมื่อรันจากโฟลเดอร์ใดก็ได้
workspace_root = Path(__file__).resolve().parents[1]
backend_path = workspace_root / "backend"
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

import pandas as pd
from backend.src.utils.logger import get_logger

logger = get_logger("openapi_exporter")
# สคริปต์ export สำหรับผู้ดูแลเรียกเอง ไม่ได้ทำงานตอน API เริ่มระบบหรือรับ request


def fetch_openapi_schema(url: str = "http://localhost:8000/openapi.json") -> dict:
    """อ่าน OpenAPI จาก server ที่รันอยู่ หรือสร้าง schema จาก FastAPI app หาก server ใช้ไม่ได้"""
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

    # หากไม่มี server ตอบ ให้ import FastAPI app แล้วสร้าง schema ในหน่วยความจำแทน
    try:
        from backend.src.main import app
        schema = app.openapi()
        logger.info("Successfully generated OpenAPI schema directly from FastAPI app instance.")
        return schema
    except Exception as ex:
        logger.error(f"Failed to generate OpenAPI schema: {ex}")
        raise ex


def parse_openapi_to_rows(schema: dict) -> list[dict]:
    """แปลง OpenAPI schema เป็นแถวข้อมูลแบน เพื่อส่งออกเป็น CSV/Excel ได้"""
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
            
            # รวมพารามิเตอร์ของ endpoint เป็นข้อความเดียว เพื่ออ่านในตารางได้ง่าย
            params = []
            for param in spec.get("parameters", []):
                p_name = param.get("name", "")
                p_in = param.get("in", "")
                p_req = "Required" if param.get("required", False) else "Optional"
                params.append(f"{p_name} ({p_in}, {p_req})")
            params_str = "; ".join(params) if params else "-"
            
            # ระบุว่า operation นี้ประกาศรับ request body หรือไม่
            req_body = "Yes" if "requestBody" in spec else "No"
            
            # เก็บ HTTP status codes ที่ประกาศใน OpenAPI เพื่อใช้เป็นข้อมูลอ้างอิง
            responses = list(spec.get("responses", {}).keys())
            responses_str = ", ".join(responses) if responses else "-"
            
            # สรุป security metadata ใน schema; เป็นข้อมูลเอกสาร ไม่ใช่การทดสอบสิทธิ์จริง
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
    """บันทึก snapshot ของ API เป็นไฟล์ CSV และ Excel ในโฟลเดอร์ที่กำหนด"""
    root_dir = Path(__file__).resolve().parents[1]
    output_path = root_dir / output_dir
    output_path.mkdir(parents=True, exist_ok=True)

    schema = fetch_openapi_schema()
    rows = parse_openapi_to_rows(schema)

    csv_file = output_path / "data" / "csv_file" / "api_snapshot.csv"
    excel_file = output_path / "data" / "excel_file" / "api_snapshot.xlsx"
    csv_file.parent.mkdir(parents=True, exist_ok=True)
    excel_file.parent.mkdir(parents=True, exist_ok=True)

    # เขียน CSV ซึ่งเปิดดูหรือนำเข้าโปรแกรมตารางคำนวณได้ง่าย
    if rows:
        fieldnames = list(rows[0].keys())
        with open(csv_file, mode="w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        logger.info(f"Successfully exported API Snapshot to CSV: {csv_file}")

    # สร้าง Excel เพิ่มถ้า dependency พร้อม; หากทำไม่ได้ CSV ที่สร้างไว้ยังใช้งานได้
    try:
        df = pd.DataFrame(rows)
        df.to_excel(excel_file, index=False, engine="openpyxl")
        logger.info(f"Successfully exported API Snapshot to Excel: {excel_file}")
    except Exception as e:
        logger.warning(f"Could not export to Excel (.xlsx): {e}")

    # แสดงสรุปใน terminal และคืน path ของไฟล์ให้สคริปต์ที่เรียกฟังก์ชันนี้
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
