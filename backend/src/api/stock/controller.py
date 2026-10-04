"""CSV upload and query endpoints for monthly and daily inventory data."""

import csv
import io
import math
from datetime import date, datetime, time
from typing import Optional

from fastapi import Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.stock.repository import StockRepository
from api.stock.schema import (
    ProductListResponse,
    StockHistoryDataPoint,
    StockHistoryResponse,
    StockRecordResponse,
    StockSummaryResponse,
    StockUploadResponse,
)
from db.database import get_db_session
from models.stock import MonthlyInventory, InventorySummary


def _as_stock_record(record) -> StockRecordResponse:
    if hasattr(record, "time") and isinstance(record.time, (date, datetime)):
        rec_time = datetime.combine(record.time, time.min) if isinstance(record.time, date) else record.time
        boxes_a = getattr(record, "boxes_A", None)
        boxes_b = getattr(record, "boxes_B", None)
        total = record.total_boxes
        prod = record.product
    else:
        rec_time = datetime.combine(record.date, time.fromisoformat(record.time))
        boxes_a = None
        boxes_b = None
        total = record.total_boxes
        prod = "Frozen Shrimp"

    return StockRecordResponse(
        id=record.id,
        recorded_at=rec_time,
        product=prod,
        boxes_A=boxes_a,
        boxes_B=boxes_b,
        total_boxes=total,
        quantity=float(total),
        unit="boxes",
        warehouse="All Zones",
        source="monthly_inventories",
        created_at=record.created_at,
    )


async def upload_csv(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db_session),
) -> StockUploadResponse:
    """Upload CSV supporting both the new format (time, product, boxes_A, boxes_B, total_boxes) and legacy format."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    try:
        decoded = (await file.read()).decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV must use UTF-8 encoding") from exc

    reader = csv.DictReader(io.StringIO(decoded))
    headers = set(reader.fieldnames or ())

    # Check if new format: time, product, boxes_A, boxes_B, total_boxes
    new_required = {"time", "product", "boxes_A", "boxes_B", "total_boxes"}
    if new_required.issubset(headers):
        repo = StockRepository(session)
        records = []
        for r in reader:
            t_str = r["time"].strip()
            if len(t_str) == 7:
                t_date = date.fromisoformat(f"{t_str}-01")
            else:
                t_date = date.fromisoformat(t_str)

            records.append(MonthlyInventory(
                time=t_date,
                product=r["product"].strip(),
                boxes_A=int(r["boxes_A"]),
                boxes_B=int(r["boxes_B"]),
                total_boxes=int(r["total_boxes"]),
            ))

        await repo.bulk_insert_monthly(records)
        return StockUploadResponse(message="Upload successful (new format)", records_inserted=len(records))

    raise HTTPException(status_code=400, detail="CSV header must contain: time, product, boxes_A, boxes_B, total_boxes")


async def get_stocks(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    split: Optional[str] = Query(None),
    time_value: Optional[str] = Query(None, alias="time"),
    product: Optional[str] = Query(None),
    warehouse: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db_session),
) -> list[StockRecordResponse]:
    repo = StockRepository(session)
    stocks = await repo.get_all_stocks(
        start_date=start_date,
        end_date=end_date,
        product=product,
        split=split or warehouse,
        time=time_value,
    )
    return [_as_stock_record(record) for record in stocks]


async def get_summary(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    product: Optional[str] = Query(None),
    split: Optional[str] = Query(None),
    time_value: Optional[str] = Query(None, alias="time"),
    session: AsyncSession = Depends(get_db_session),
) -> StockSummaryResponse:
    repo = StockRepository(session)
    summary_data = await repo.get_summary(start_date=start_date, end_date=end_date, product=product)
    if isinstance(summary_data["latest_record"], date):
        summary_data["latest_record"] = datetime.combine(summary_data["latest_record"], time.min)
    return StockSummaryResponse(**summary_data)


async def get_products(
    session: AsyncSession = Depends(get_db_session),
) -> ProductListResponse:
    repo = StockRepository(session)
    prods = await repo.get_products()
    return ProductListResponse(products=prods)


async def get_history(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    product: Optional[str] = Query(None),
    split: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db_session),
) -> StockHistoryResponse:
    repo = StockRepository(session)
    stocks = await repo.get_history(product=product, start_date=start_date, end_date=end_date)
    requested_product = product or "Frozen Shrimp"
    data = []
    for r in stocks:
        if hasattr(r, "time"):
            rec_date = datetime.combine(r.time, time.min) if isinstance(r.time, date) else r.time
            boxes_a = getattr(r, "boxes_A", None)
            boxes_b = getattr(r, "boxes_B", None)
            total = r.total_boxes
            prod = r.product
        else:
            rec_date = datetime.combine(r.date, time.fromisoformat(r.time))
            boxes_a = None
            boxes_b = None
            total = r.total_boxes
            prod = requested_product

        data.append(StockHistoryDataPoint(
            recorded_at=rec_date,
            product=prod,
            quantity=float(total),
            boxes_A=boxes_a,
            boxes_B=boxes_b,
            total_boxes=total,
        ))

    return StockHistoryResponse(data=data)
