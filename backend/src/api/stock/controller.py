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


async def upload_csv(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db_session)
) -> StockUploadResponse:
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be a CSV")

    content = await file.read()
    decoded = content.decode("utf-8")
    reader = csv.DictReader(io.StringIO(decoded))
    
    # Required columns based on spec
    required_cols = {"date", "product", "quantity", "unit", "warehouse"}
    if not reader.fieldnames or not required_cols.issubset(set(reader.fieldnames)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Missing required columns. Expected at least: {required_cols}"
        )

    repo = StockRepository(session)
    records_to_insert = []
    
    # Validate and Parse
    try:
        for row_index, row in enumerate(reader, start=2): # Row 1 is header
            # Extract and clean
            date_str = row.get("date", "").strip()
            product = row.get("product", "").strip()
            quantity_str = row.get("quantity", "").strip()
            unit = row.get("unit", "").strip()
            warehouse = row.get("warehouse", "").strip() or None
            
            # Check missing
            if not date_str:
                raise HTTPException(status_code=400, detail={"row": row_index, "column": "date", "reason": "Missing value"})
            if not product:
                raise HTTPException(status_code=400, detail={"row": row_index, "column": "product", "reason": "Missing value"})
            if not quantity_str:
                raise HTTPException(status_code=400, detail={"row": row_index, "column": "quantity", "reason": "Missing value"})
            if not unit:
                raise HTTPException(status_code=400, detail={"row": row_index, "column": "unit", "reason": "Missing value"})

            # Validate data types
            try:
                # Support ISO format or common formats like YYYY-MM-DD
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
            
            # Check duplicates in DB
            is_dup = await repo.check_duplicate(recorded_at, product, warehouse)
            if is_dup:
                raise HTTPException(status_code=400, detail={"row": row_index, "column": "all", "reason": f"Duplicate entry found for {product} on {date_str} at {warehouse}"})

            record = ShrimpStockData(
                recorded_at=recorded_at,
                product=product,
                quantity=quantity,
                unit=unit,
                warehouse=warehouse,
                source="csv"
            )
            records_to_insert.append(record)
            
        if not records_to_insert:
            raise HTTPException(status_code=400, detail="CSV is empty or valid records not found")
            
        await repo.bulk_insert(records_to_insert)
            
    except HTTPException:
        # Nested transaction will auto-rollback on exception
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
