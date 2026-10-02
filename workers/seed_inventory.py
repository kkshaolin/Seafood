"""Idempotently import the inventory CSV into PostgreSQL."""

import asyncio
import csv
import logging
import math
import os
import sys
from datetime import date, time
from pathlib import Path

from sqlalchemy import insert, select, text

backend_src = Path(
    os.getenv("BACKEND_SRC", Path(__file__).resolve().parents[1] / "backend" / "src")
)
sys.path.insert(0, str(backend_src))

from db.database import Base, engine
from models.stock import InventorySummary
from inventory_data import get_inventory_csv_path

logger = logging.getLogger("seed_inventory")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

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
    "image",
    "split",
    "date",
    "time",
    *INTEGER_COLUMNS,
    *FLOAT_COLUMNS,
}


def _read_inventory_rows(csv_path: Path) -> list[InventorySummary]:
    records = []
    with csv_path.open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or ())
        if missing:
            raise ValueError(
                f"Inventory CSV is missing required columns: {', '.join(sorted(missing))}"
            )

        for row_number, row in enumerate(reader, start=2):
            try:
                recorded_date = date.fromisoformat(row["date"].strip())
                recorded_time = time.fromisoformat(row["time"].strip()).isoformat(
                    timespec="minutes"
                )
                integer_values = {name: int(row[name]) for name in INTEGER_COLUMNS}
                float_values = {name: float(row[name]) for name in FLOAT_COLUMNS}
                if not all(math.isfinite(value) for value in float_values.values()):
                    raise ValueError("numeric fields must be finite")
                if not row["split"].strip() or not row["image"].strip():
                    raise ValueError("image and split must not be empty")
            except (AttributeError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid inventory CSV row {row_number} in {csv_path}: {exc}"
                ) from exc

            records.append(
                InventorySummary(
                    image_path=row["image"].strip(),
                    split=row["split"].strip(),
                    date=recorded_date,
                    time=recorded_time,
                    **integer_values,
                    **float_values,
                )
            )

    if not records:
        raise ValueError(f"Inventory CSV contains no data rows: {csv_path}")
    return records


async def _upgrade_inventory_schema(connection) -> None:
    await connection.execute(
        text("ALTER TABLE inventory_summaries ADD COLUMN IF NOT EXISTS id SERIAL")
    )
    await connection.execute(
        text(
            "ALTER TABLE inventory_summaries "
            "ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now()"
        )
    )
    result = await connection.execute(
        text(
            """
            SELECT column_name, data_type, character_maximum_length,
                   is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'inventory_summaries'
            """
        )
    )
    columns = {row.column_name: row for row in result}
    expected_columns = {
        "image_path": ("character varying", 255, "VARCHAR(255)"),
        "split": ("character varying", 50, "VARCHAR(50)"),
        "date": ("date", None, "DATE"),
        "time": ("character varying", 10, "VARCHAR(10)"),
        "total_boxes": ("integer", None, "INTEGER"),
        "total_weight_kg": ("double precision", None, "DOUBLE PRECISION"),
        "occupied_slots": ("integer", None, "INTEGER"),
        "empty_slots": ("integer", None, "INTEGER"),
        "occupancy_pct": ("double precision", None, "DOUBLE PRECISION"),
        "boxes_level1": ("integer", None, "INTEGER"),
        "boxes_level2": ("integer", None, "INTEGER"),
        "boxes_level3": ("integer", None, "INTEGER"),
        "boxes_level4": ("integer", None, "INTEGER"),
        "inbound_boxes": ("integer", None, "INTEGER"),
        "outbound_boxes": ("integer", None, "INTEGER"),
        "cold_room_temp_c": ("double precision", None, "DOUBLE PRECISION"),
        "humidity_pct": ("double precision", None, "DOUBLE PRECISION"),
        "id": ("integer", None, "INTEGER"),
        "created_at": ("timestamp with time zone", None, "TIMESTAMPTZ"),
    }
    missing = expected_columns.keys() - columns.keys()
    if missing:
        raise ValueError(
            "Cannot upgrade inventory_summaries; missing columns: "
            + ", ".join(sorted(missing))
        )

    for name, (data_type, max_length, sql_type) in expected_columns.items():
        column = columns[name]
        if column.data_type != data_type or (
            max_length is not None and column.character_maximum_length != max_length
        ):
            await connection.execute(
                text(
                    f"ALTER TABLE inventory_summaries ALTER COLUMN {name} "
                    f"TYPE {sql_type} USING {name}::{sql_type}"
                )
            )
        if name == "created_at":
            await connection.execute(
                text("UPDATE inventory_summaries SET created_at = now() WHERE created_at IS NULL")
            )
        if column.is_nullable == "YES":
            await connection.execute(
                text(f"ALTER TABLE inventory_summaries ALTER COLUMN {name} SET NOT NULL")
            )
        if name == "created_at" and column.column_default is None:
            await connection.execute(
                text("ALTER TABLE inventory_summaries ALTER COLUMN created_at SET DEFAULT now()")
            )

    await connection.execute(
        text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conrelid = 'inventory_summaries'::regclass
                      AND contype = 'p'
                ) THEN
                    ALTER TABLE inventory_summaries
                    ADD CONSTRAINT inventory_summaries_pkey PRIMARY KEY (id);
                END IF;
            END
            $$
            """
        )
    )


async def _upgrade_forecast_schema(connection) -> None:
    result = await connection.execute(
        text(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'forecast_results'
              AND column_name = 'model_version'
            """
        )
    )
    column = result.first()
    if column is None:
        raise ValueError("Cannot upgrade forecast_results; model_version column is missing")
    if column.data_type != "text":
        await connection.execute(
            text(
                "ALTER TABLE forecast_results ALTER COLUMN model_version "
                "TYPE TEXT USING model_version::TEXT"
            )
        )


async def seed_inventory() -> int:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await _upgrade_inventory_schema(connection)
        await _upgrade_forecast_schema(connection)

    try:
        csv_path = get_inventory_csv_path()
        records = _read_inventory_rows(csv_path)
    except (FileNotFoundError, ValueError) as exc:
        logger.warning(
            "Inventory CSV not available (%s); database tables initialized successfully without seed records.",
            exc,
        )
        return 0

    async with engine.begin() as connection:
        deduplicated = await connection.execute(
            text(
                """
                WITH ranked AS (
                    SELECT id, row_number() OVER (
                        PARTITION BY date, time, split, image_path, total_boxes,
                            total_weight_kg, occupied_slots, empty_slots, occupancy_pct,
                            boxes_level1, boxes_level2, boxes_level3, boxes_level4,
                            inbound_boxes, outbound_boxes, cold_room_temp_c, humidity_pct
                        ORDER BY id
                    ) AS row_number
                    FROM inventory_summaries
                )
                DELETE FROM inventory_summaries AS inventory
                USING ranked
                WHERE inventory.id = ranked.id AND ranked.row_number > 1
                """
            )
        )
        if deduplicated.rowcount > 0:
            logger.warning("Removed %d identical duplicate inventory rows", deduplicated.rowcount)
        await connection.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_inventory_summary_observation
                ON inventory_summaries (date, time, split)
                """
            )
        )

    async with engine.begin() as connection:
        result = await connection.execute(
            select(InventorySummary.date, InventorySummary.time, InventorySummary.split)
        )
        existing_keys = {tuple(row) for row in result.all()}
        pending = []
        seen_keys = set()
        for record in records:
            key = (record.date, record.time, record.split)
            if key not in existing_keys and key not in seen_keys:
                pending.append(record)
                seen_keys.add(key)
        if pending:
            values = [
                {
                    column.name: getattr(record, column.name)
                    for column in InventorySummary.__table__.columns
                    if column.name not in {"id", "created_at"}
                }
                for record in pending
            ]
            await connection.execute(insert(InventorySummary), values)

    logger.info(
        "Loaded %d inventory rows from %s (%d inserted, %d already present)",
        len(records),
        csv_path,
        len(pending),
        len(records) - len(pending),
    )
    return len(pending)


async def main() -> None:
    try:
        await seed_inventory()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
