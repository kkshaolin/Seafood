"""Controller สำหรับจัดการ CSV upload และ query สต็อกสินค้า.

โค้ดนี้แยกการ validate, parse, duplicate check และ bulk insert ออกจาก repository เพื่อให้ logic
ของ API ชัดเจนและลดความซับซ้อนของ route handler.
"""

import csv
import io
from datetime import datetime, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db_session
from models.stock import ShrimpStockData
from api.stock.repository import StockRepository
from api.stock.schema import (
    StockUploadResponse,
    StockRecordResponse,
    StockSummaryResponse,
    StockHistoryResponse,
    StockHistoryDataPoint,
    ProductListResponse
)


def _parse_and_validate_row(row: dict, row_index: int) -> dict:
    """
    ฟังก์ชันช่วยสำหรับตรวจสอบและแปลงข้อมูลแต่ละแถวใน CSV
    แยกโค้ดออกมาเพื่อเพิ่มความอ่านง่าย (Readability) และลดความซับซ้อน (Cyclomatic Complexity)
    """
    date_str = row.get("date", "").strip()
    product = row.get("product", "").strip()
    quantity_str = row.get("quantity", "").strip()
    unit = row.get("unit", "").strip()
    warehouse = row.get("warehouse", "").strip() or None
    
    # ตรวจสอบค่าว่าง
    if not date_str:
        raise HTTPException(status_code=400, detail={"row": row_index, "column": "date", "reason": "Missing value"})
    if not product:
        raise HTTPException(status_code=400, detail={"row": row_index, "column": "product", "reason": "Missing value"})
    if not quantity_str:
        raise HTTPException(status_code=400, detail={"row": row_index, "column": "quantity", "reason": "Missing value"})
    if not unit:
        raise HTTPException(status_code=400, detail={"row": row_index, "column": "unit", "reason": "Missing value"})

    # แปลงชนิดข้อมูล (Type Casting)
    try:
        recorded_at = datetime.fromisoformat(date_str)
    except ValueError:
        try:
            recorded_at = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail={"row": row_index, "column": "date", "reason": "Invalid date format, use YYYY-MM-DD"})
            
    from datetime import timezone
    if recorded_at.tzinfo is None:
        recorded_at = recorded_at.replace(tzinfo=timezone.utc)
        
    try:
        quantity = float(quantity_str)
    except ValueError:
        raise HTTPException(status_code=400, detail={"row": row_index, "column": "quantity", "reason": "Must be a number"})
        
    return {
        "recorded_at": recorded_at,
        "product": product,
        "quantity": quantity,
        "unit": unit,
        "warehouse": warehouse,
        "date_str": date_str # เก็บไว้ใช้สำหรับแสดง error message
    }


async def upload_csv(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db_session)
) -> StockUploadResponse:
    """
    อัปโหลดข้อมูล Stock แบบ Bulk จากไฟล์ CSV
    ถูก Refactor เพื่อลดปัญหา N+1 Query และแยก Logic การตรวจสอบออกมาต่างหาก
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be a CSV")

    content = await file.read()
    decoded = content.decode("utf-8")
    reader = list(csv.DictReader(io.StringIO(decoded)))
    
    if not reader:
        raise HTTPException(status_code=400, detail="CSV is empty")
        
    required_cols = {"date", "product", "quantity", "unit", "warehouse"}
    if not set(reader[0].keys()).issuperset(required_cols):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Missing required columns. Expected at least: {required_cols}"
        )

    repo = StockRepository(session)
    
    try:
        # 1. Parse and validate all rows first (In-memory validation)
        parsed_records = []
        for row_index, row in enumerate(reader, start=2):
            parsed_records.append(_parse_and_validate_row(row, row_index))
            
        # 2. Bulk check for duplicates (Performance Optimization: O(1) query instead of O(N))
        existing_keys = await repo.get_existing_keys(parsed_records)
        
        records_to_insert = []
        for row_index, parsed in enumerate(parsed_records, start=2):
            # ตรวจสอบซ้ำกับฐานข้อมูล
            key = (parsed["recorded_at"], parsed["product"], parsed["warehouse"])
            if key in existing_keys:
                raise HTTPException(
                    status_code=400, 
                    detail={"row": row_index, "column": "all", "reason": f"Duplicate entry found for {parsed['product']} on {parsed['date_str']} at {parsed['warehouse']}"}
                )
                
            # แปลงเป็น Model ก่อนบันทึก
            records_to_insert.append(ShrimpStockData(
                recorded_at=parsed["recorded_at"],
                product=parsed["product"],
                quantity=parsed["quantity"],
                unit=parsed["unit"],
                warehouse=parsed["warehouse"],
                source="csv"
            ))

        # 3. Bulk Insert
        await repo.bulk_insert(records_to_insert)
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return StockUploadResponse(message="Upload successful", records_inserted=len(records_to_insert))


async def get_stocks(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    product: Optional[str] = Query(None),
    warehouse: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db_session)
) -> List[StockRecordResponse]:
    repo = StockRepository(session)
    stocks = await repo.get_all_stocks(start_date, end_date, product, warehouse)
    return [StockRecordResponse.model_validate(s) for s in stocks]


async def get_summary(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    product: Optional[str] = Query(None),
    warehouse: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db_session)
) -> StockSummaryResponse:
    repo = StockRepository(session)
    summary_data = await repo.get_summary(start_date, end_date, product, warehouse)
    return StockSummaryResponse(**summary_data)


async def get_products(
    session: AsyncSession = Depends(get_db_session)
) -> ProductListResponse:
    repo = StockRepository(session)
    products = await repo.get_products()
    return ProductListResponse(products=products)


async def get_history(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    product: Optional[str] = Query(None),
    warehouse: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db_session)
) -> StockHistoryResponse:
    repo = StockRepository(session)
    stocks = await repo.get_all_stocks(start_date, end_date, product, warehouse)
    # Sort history chronologically for charts
    stocks.sort(key=lambda x: x.recorded_at)
    data = [StockHistoryDataPoint(recorded_at=s.recorded_at, product=s.product, quantity=s.quantity) for s in stocks]
    return StockHistoryResponse(data=data)
