"""CSV upload and query endpoints for inventory summaries."""

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
from models.stock import InventorySummary

INTEGER_COLUMNS = (
    "total_boxes",
    "occupied_slots",
    "empty_slots",
    "boxes_level1",
    "boxes_level2",
    "boxes_level3",
    "inbound_boxes",
    "outbound_boxes",
)
FLOAT_COLUMNS = (
    "total_weight_kg",
    "occupancy_pct",
    "cold_room_temp_c",
    "humidity_pct",
)
REQUIRED_COLUMNS = {
    "split",
    "date",
    "time",
    *INTEGER_COLUMNS,
    *FLOAT_COLUMNS,
}


def _parse_inventory_row(row: dict[str, str], row_index: int) -> InventorySummary:
    image_path = (row.get("image_path") or row.get("image") or "").strip()
    split = (row.get("split") or "").strip()
    try:
        recorded_date = date.fromisoformat(row["date"].strip())
        recorded_time = time.fromisoformat(row["time"].strip()).isoformat(timespec="minutes")
        integer_values = {name: int(row[name]) for name in INTEGER_COLUMNS}
        float_values = {name: float(row[name]) for name in FLOAT_COLUMNS}
        if not all(math.isfinite(value) for value in float_values.values()):
            raise ValueError("numeric fields must be finite")
        if not image_path or not split:
            raise ValueError("image and split must not be empty")
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"row": row_index, "reason": str(exc)},
        ) from exc

    return InventorySummary(
        image_path=image_path,
        split=split,
        date=recorded_date,
        time=recorded_time,
        **integer_values,
        **float_values,
    )


def _as_stock_record(record: InventorySummary) -> StockRecordResponse:
    return StockRecordResponse(
        id=record.id,
        recorded_at=datetime.combine(record.date, time.fromisoformat(record.time)),
        product="Inventory",
        quantity=record.total_boxes,
        unit="boxes",
        warehouse=record.split,
        source="inventory_csv",
        created_at=record.created_at,
    )


async def upload_csv(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db_session),
) -> StockUploadResponse:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    try:
        decoded = (await file.read()).decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV must use UTF-8 encoding") from exc

    reader = csv.DictReader(io.StringIO(decoded))
    missing = REQUIRED_COLUMNS - set(reader.fieldnames or ())
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required columns: {', '.join(sorted(missing))}",
        )

    records = [
        _parse_inventory_row(row, row_index)
        for row_index, row in enumerate(reader, start=2)
    ]
    if not records:
        raise HTTPException(status_code=400, detail="CSV contains no data rows")

    keys = [(record.date, record.split, record.time) for record in records]
    if len(set(keys)) != len(keys):
        raise HTTPException(status_code=400, detail="CSV contains duplicate inventory rows")

    repo = StockRepository(session)
    existing_keys = await repo.get_existing_keys(
        [{"date": record.date, "split": record.split, "time": record.time} for record in records]
    )
    duplicates = set(keys) & existing_keys
    if duplicates:
        raise HTTPException(
            status_code=400,
            detail=f"Database already contains {len(duplicates)} inventory row(s) from this CSV",
        )

    await repo.bulk_insert(records)
    return StockUploadResponse(message="Upload successful", records_inserted=len(records))


async def get_stocks(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    split: Optional[str] = Query(None),
    time_value: Optional[str] = Query(None, alias="time"),
    product: Optional[str] = Query(None, description="Retained for compatibility; inventory data has no product column"),
    warehouse: Optional[str] = Query(None, description="Alias for split"),
    session: AsyncSession = Depends(get_db_session),
) -> list[StockRecordResponse]:
    # This column has no product dimension; retain the old query parameter without filtering.
    _ = product
    repo = StockRepository(session)
    stocks = await repo.get_all_stocks(
        start_date,
        end_date,
        split or warehouse,
        time_value,
    )
    return [_as_stock_record(record) for record in stocks]


async def get_summary(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    split: Optional[str] = Query(None),
    time_value: Optional[str] = Query(None, alias="time"),
    session: AsyncSession = Depends(get_db_session),
) -> StockSummaryResponse:
    repo = StockRepository(session)
    summary_data = await repo.get_summary(start_date, end_date, split, time_value)
    if isinstance(summary_data["latest_record"], date):
        summary_data["latest_record"] = datetime.combine(summary_data["latest_record"], time.min)
    return StockSummaryResponse(**summary_data)


async def get_products(
    session: AsyncSession = Depends(get_db_session),
) -> ProductListResponse:
    repo = StockRepository(session)
    return ProductListResponse(products=["Inventory"] if await repo.get_splits() else [])


async def get_history(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    product: Optional[str] = Query(None, description="Retained for compatibility; inventory data has no product column"),
    split: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db_session),
) -> StockHistoryResponse:
    repo = StockRepository(session)
    stocks = await repo.get_all_stocks(start_date, end_date, split)
    stocks.sort(key=lambda record: (record.date, record.time))
    requested_product = product or "Inventory"
    data = [
        StockHistoryDataPoint(
            recorded_at=datetime.combine(record.date, time.fromisoformat(record.time)),
            product=requested_product,
            quantity=record.total_boxes,
        )
        for record in stocks
    ]
    return StockHistoryResponse(data=data)
