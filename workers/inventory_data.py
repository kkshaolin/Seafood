"""Shared path and CSV loading helpers for the inventory time series."""

import csv
import os
import re
from datetime import date, datetime, time
from pathlib import Path

import pandas as pd


def get_inventory_csv_path() -> Path:
    configured_path = os.getenv("INVENTORY_CSV_PATH")
    if configured_path:
        path = Path(configured_path)
        if not path.is_file():
            raise FileNotFoundError(f"INVENTORY_CSV_PATH does not exist: {path}")
        return path

    storage_root = Path(
        os.getenv("STORAGE_ROOT", Path(__file__).resolve().parents[1] / "storage")
    )
    candidates = (
        storage_root / "data" / "csvfile" / "inventory" / "inventory_summary.csv",
        storage_root / "data" / "csv_file" / "inventory_summary (1).csv",
    )
    for path in candidates:
        if path.is_file():
            return path

    raise FileNotFoundError(
        "Inventory CSV not found; expected "
        f"{candidates[0]} (legacy fallback: {candidates[1]})"
    )


def get_local_arima_model_path(product: str) -> Path:
    storage_root = Path(
        os.getenv("STORAGE_ROOT", Path(__file__).resolve().parents[1] / "storage")
    )
    safe_product = re.sub(r"[^A-Za-z0-9_.-]", "_", product)
    filename = (
        "arima_premium_shrimp.pkl"
        if product == "Premium_White_Shrimp"
        else f"arima_{safe_product}.pkl"
    )
    return storage_root / "models" / "time_serie" / filename


def load_inventory_time_series(csv_path: Path | None = None) -> pd.DataFrame:
    """Load inventory rows as recorded_at/quantity for training and prediction."""
    path = csv_path or get_inventory_csv_path()
    records = []
    required_columns = {"date", "time", "total_boxes"}

    with path.open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        columns = set(reader.fieldnames or ())
        missing = required_columns - columns
        if missing:
            raise ValueError(
                f"Inventory CSV {path} is missing required columns: "
                f"{', '.join(sorted(missing))}"
            )

        for row_number, row in enumerate(reader, start=2):
            try:
                recorded_at = datetime.combine(
                    date.fromisoformat(row["date"].strip()),
                    time.fromisoformat(row["time"].strip()),
                )
                quantity = float(row["total_boxes"])
            except (AttributeError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid inventory CSV row {row_number} in {path}: {exc}"
                ) from exc
            if not pd.notna(quantity) or quantity in (float("inf"), float("-inf")):
                raise ValueError(f"Invalid inventory CSV row {row_number} in {path}: total_boxes must be finite")
            records.append({"recorded_at": recorded_at, "quantity": quantity})

    if not records:
        raise ValueError(f"Inventory CSV contains no data rows: {path}")
    return pd.DataFrame.from_records(records)
