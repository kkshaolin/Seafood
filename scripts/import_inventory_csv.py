"""Import CSV data into PostgreSQL for monthly_inventories, daily_inventories, and yearly_inventories using asyncpg."""

import asyncio
import csv
import os
import sys
from datetime import date, datetime
from pathlib import Path
import asyncpg

# Paths
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
CSV_DIR = WORKSPACE_ROOT / "storage" / "data" / "csv_file"
MONTHLY_CSV = CSV_DIR / "shrimp_stock_6years_mont.csv"
DAILY_CSV = CSV_DIR / "shrimp_stock_daily_6years.csv"

# DB Connection settings (Docker host: localhost:5433, or inside docker: postgres:5432)
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = int(os.getenv("POSTGRES_PORT", "5433"))
DB_NAME = os.getenv("POSTGRES_DB", "my_database")
DB_USER = os.getenv("POSTGRES_USER", "admin")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "secretpassword")

DDL = """
-- 1. การเก็บค่าจากกล่อง / กล้องตรวจจับ (Box Logs) - ว่างไว้ก่อน
CREATE TABLE IF NOT EXISTS box_logs (
    id BIGSERIAL PRIMARY KEY,
    time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    product VARCHAR(100) NOT NULL DEFAULT 'Frozen Shrimp',
    boxes_A INT NOT NULL DEFAULT 0,
    boxes_B INT NOT NULL DEFAULT 0,
    total_boxes INT NOT NULL DEFAULT 0,
    camera_id VARCHAR(50),
    image_path VARCHAR(255),
    confidence REAL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_box_logs_time ON box_logs(time);

-- 2. คลังสินค้ารายวัน (Daily Inventories)
CREATE TABLE IF NOT EXISTS daily_inventories (
    id SERIAL PRIMARY KEY,
    time DATE NOT NULL,
    product VARCHAR(100) NOT NULL DEFAULT 'Frozen Shrimp',
    boxes_A INT NOT NULL DEFAULT 0,
    boxes_B INT NOT NULL DEFAULT 0,
    total_boxes INT NOT NULL DEFAULT 0,
    inbound_boxes INT NOT NULL DEFAULT 0,
    outbound_boxes INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_daily_inventories_time_product UNIQUE (time, product)
);
CREATE INDEX IF NOT EXISTS idx_daily_inventories_time ON daily_inventories(time);

-- 3. คลังสินค้ารายเดือน (Monthly Inventories)
CREATE TABLE IF NOT EXISTS monthly_inventories (
    id SERIAL PRIMARY KEY,
    time DATE NOT NULL,
    product VARCHAR(100) NOT NULL DEFAULT 'Frozen Shrimp',
    boxes_A INT NOT NULL DEFAULT 0,
    boxes_B INT NOT NULL DEFAULT 0,
    total_boxes INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_monthly_inventories_time_product UNIQUE (time, product)
);
CREATE INDEX IF NOT EXISTS idx_monthly_inventories_time ON monthly_inventories(time);

-- 3.1 คลังสินค้ารายปี (Yearly Inventories)
CREATE TABLE IF NOT EXISTS yearly_inventories (
    id SERIAL PRIMARY KEY,
    time DATE NOT NULL,
    product VARCHAR(100) NOT NULL DEFAULT 'Frozen Shrimp',
    boxes_A INT NOT NULL DEFAULT 0,
    boxes_B INT NOT NULL DEFAULT 0,
    total_boxes INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_yearly_inventories_time_product UNIQUE (time, product)
);
CREATE INDEX IF NOT EXISTS idx_yearly_inventories_time ON yearly_inventories(time);

-- 4. ค่าทำนายจาก ARIMA (ARIMA Forecasts) - ว่างไว้ก่อน
CREATE TABLE IF NOT EXISTS arima_forecasts (
    id SERIAL PRIMARY KEY,
    time DATE NOT NULL,
    product VARCHAR(100) NOT NULL DEFAULT 'Frozen Shrimp',
    boxes_A REAL,
    boxes_B REAL,
    total_boxes REAL NOT NULL,
    lower_bound REAL,
    upper_bound REAL,
    model_order VARCHAR(50) DEFAULT 'ARIMA(1,1,1)',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_arima_forecasts_time_product ON arima_forecasts(time, product);
"""


async def run_import():
    print(f"Connecting to PostgreSQL at {DB_HOST}:{DB_PORT}/{DB_NAME} as {DB_USER}...")
    conn = await asyncpg.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )

    print("Creating tables (if not exist)...")
    await conn.execute(DDL)
    print("Tables ensured successfully.")

    # 1. Load Monthly CSV
    if not MONTHLY_CSV.exists():
        print(f"Error: Monthly CSV not found at {MONTHLY_CSV}")
        return
    
    print(f"Reading monthly CSV: {MONTHLY_CSV}")
    monthly_rows = []
    with open(MONTHLY_CSV, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            t_str = r["time"].strip()
            if len(t_str) == 7:
                t_date = date.fromisoformat(f"{t_str}-01")
            else:
                t_date = date.fromisoformat(t_str)
            
            monthly_rows.append((
                t_date,
                r["product"].strip(),
                int(r["boxes_A"]),
                int(r["boxes_B"]),
                int(r["total_boxes"])
            ))

    print(f"Found {len(monthly_rows)} monthly rows. Inserting into monthly_inventories...")
    await conn.execute("TRUNCATE TABLE monthly_inventories RESTART IDENTITY;")
    await conn.executemany(
        """
        INSERT INTO monthly_inventories (time, product, boxes_A, boxes_B, total_boxes)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (time, product) DO UPDATE SET
            boxes_A = EXCLUDED.boxes_A,
            boxes_B = EXCLUDED.boxes_B,
            total_boxes = EXCLUDED.total_boxes;
        """,
        monthly_rows
    )
    count_m = await conn.fetchval("SELECT COUNT(*) FROM monthly_inventories;")
    print(f"-> monthly_inventories now has {count_m} rows.")

# 2. Load Daily CSV
    if not DAILY_CSV.exists():
        print(f"Error: Daily CSV not found at {DAILY_CSV}")
        return

    print(f"Reading daily CSV: {DAILY_CSV}")
    daily_rows = []
    with open(DAILY_CSV, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            t_str = r["time"].strip()
            t_date = date.fromisoformat(t_str)
            daily_rows.append((
                t_date,
                r["product"].strip(),
                int(r["boxes_A"]),
                int(r["boxes_B"]),
                int(r["total_boxes"]),
                0,  # กำหนดค่า inbound_boxes เป็น 0
                0   # กำหนดค่า outbound_boxes เป็น 0
            ))

    print(f"Found {len(daily_rows)} daily rows. Inserting into daily_inventories...")
    await conn.execute("TRUNCATE TABLE daily_inventories RESTART IDENTITY;")
    await conn.executemany(
        """
        INSERT INTO daily_inventories (time, product, boxes_A, boxes_B, total_boxes, inbound_boxes, outbound_boxes)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (time, product) DO UPDATE SET
            boxes_A = EXCLUDED.boxes_A,
            boxes_B = EXCLUDED.boxes_B,
            total_boxes = EXCLUDED.total_boxes;
        """,
        daily_rows
    )
    count_d = await conn.fetchval("SELECT COUNT(*) FROM daily_inventories;")
    print(f"-> daily_inventories now has {count_d} rows.")

    # 3. Populate Yearly Inventories (Aggregated by year from monthly)
    print("Generating yearly_inventories aggregated by year...")
    await conn.execute("TRUNCATE TABLE yearly_inventories RESTART IDENTITY;")
    await conn.execute("""
        INSERT INTO yearly_inventories (time, product, boxes_A, boxes_B, total_boxes)
        SELECT 
            DATE_TRUNC('year', time)::DATE as time,
            product,
            SUM(boxes_A) as boxes_A,
            SUM(boxes_B) as boxes_B,
            SUM(total_boxes) as total_boxes
        FROM monthly_inventories
        GROUP BY DATE_TRUNC('year', time)::DATE, product
        ORDER BY time;
    """)
    y_row = await conn.fetchrow("SELECT COUNT(*), MIN(time), MAX(time) FROM yearly_inventories;")
    print(f"-> yearly_inventories now has {y_row[0]} rows (from {y_row[1]} to {y_row[2]}).")

    await conn.close()
    print("\nAll requested data imported successfully!")


def main():
    asyncio.run(run_import())


if __name__ == "__main__":
    main()
