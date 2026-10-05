"""Sync script to pull dataset and historical records from Supabase to Local PostgreSQL.

Usage:
    python scripts/sync_from_supabase.py
    python scripts/sync_from_supabase.py --tables monthly_inventories,box_logs
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import List, Optional

import asyncpg

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env if present
env_file = PROJECT_ROOT / ".env"
if env_file.exists():
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

DEFAULT_SUPABASE_URL = os.getenv(
    "SUPABASE_DATABASE_URL",
    "postgresql://postgres.hmystckhrffpnspzbpue:r5Diz%24x6g8-Ls3%25@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres"
)
DEFAULT_LOCAL_URL = os.getenv(
    "LOCAL_DATABASE_URL",
    "postgresql://admin:secretpassword@localhost:5433/my_database"
)

SYNC_TABLES = [
    "monthly_inventories",
    "daily_inventories",
    "yearly_inventories",
    "box_logs",
    "arima_forecasts",
    "inventory_summaries",
    "camera_logs",
]


async def sync_table(src_conn: asyncpg.Connection, dest_conn: asyncpg.Connection, table_name: str) -> int:
    """Sync a single table from Supabase to local PostgreSQL."""
    # Check if table exists in source
    src_exists = await src_conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = $1 AND table_schema = 'public')",
        table_name
    )
    if not src_exists:
        print(f"  [-] Table '{table_name}' does not exist in Supabase. Skipping.")
        return 0

    # Check if table exists in dest
    dest_exists = await dest_conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = $1 AND table_schema = 'public')",
        table_name
    )
    if not dest_exists:
        print(f"  [-] Table '{table_name}' does not exist in Local PostgreSQL. Skipping.")
        return 0

    # Get column names
    columns = await src_conn.fetch(
        """
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = $1 AND table_schema = 'public'
        ORDER BY ordinal_position
        """,
        table_name
    )
    col_names = [r["column_name"] for r in columns]
    if not col_names:
        return 0

    cols_str = ", ".join(f'"{c}"' for c in col_names)
    placeholders = ", ".join(f"${i+1}" for i in range(len(col_names)))

    # Fetch rows from source
    rows = await src_conn.fetch(f'SELECT {cols_str} FROM "{table_name}"')
    if not rows:
        print(f"  [i] Table '{table_name}' has 0 rows in Supabase.")
        return 0

    # Truncate and insert into dest
    await dest_conn.execute(f'TRUNCATE TABLE "{table_name}" CASCADE;')
    
    # Bulk insert in batches of 500
    batch_size = 500
    inserted = 0
    insert_sql = f'INSERT INTO "{table_name}" ({cols_str}) VALUES ({placeholders})'

    for i in range(0, len(rows), batch_size):
        batch = rows[i:i+batch_size]
        batch_values = [tuple(r.values()) for r in batch]
        await dest_conn.executemany(insert_sql, batch_values)
        inserted += len(batch)

    print(f"  [+] Synced '{table_name}': {inserted} rows transferred.")
    return inserted


async def reset_sequences(conn: asyncpg.Connection):
    """Reset all sequence values to max(column) + 1 to avoid duplicate key errors on future inserts."""
    rows = await conn.fetch("""
        SELECT 
            t.relname AS table_name,
            a.attname AS column_name,
            s.relname AS sequence_name
        FROM pg_class s
        JOIN pg_depend d ON d.objid = s.oid
        JOIN pg_class t ON d.refobjid = t.oid
        JOIN pg_attribute a ON d.refobjid = a.attrelid AND d.refobjsubid = a.attnum
        WHERE s.relkind = 'S'
    """)
    for r in rows:
        tbl = r['table_name']
        col = r['column_name']
        seq = r['sequence_name']
        max_val = await conn.fetchval(f'SELECT COALESCE(MAX("{col}"), 0) FROM "{tbl}"')
        new_val = max(max_val, 1)
        is_called = "true" if max_val > 0 else "false"
        await conn.execute(f"SELECT setval('{seq}', {new_val}, {is_called})")
    print("  [+] All database ID sequences reset to MAX(id).")


async def main():
    parser = argparse.ArgumentParser(description="Sync data from Supabase to Local PostgreSQL")
    parser.add_argument("--src", default=DEFAULT_SUPABASE_URL, help="Supabase Database URL")
    parser.add_argument("--dest", default=DEFAULT_LOCAL_URL, help="Local PostgreSQL Database URL")
    parser.add_argument("--tables", default="", help="Comma-separated list of tables to sync")
    args = parser.parse_args()

    tables = [t.strip() for t in args.tables.split(",") if t.strip()] or SYNC_TABLES

    print("==========================================================")
    print("      SUPABASE -> LOCAL POSTGRESQL DATA SYNCHRONIZER      ")
    print("==========================================================")
    print(f"Source (Supabase): {args.src.split('@')[-1]}")
    print(f"Dest   (Local PG): {args.dest.split('@')[-1]}")
    print(f"Target Tables    : {', '.join(tables)}")
    print("----------------------------------------------------------")

    try:
        src_conn = await asyncpg.connect(args.src, statement_cache_size=0)
        print("[OK] Connected to Supabase!")
    except Exception as e:
        print(f"[ERR] Failed to connect to Supabase: {e}")
        return

    try:
        dest_conn = await asyncpg.connect(args.dest)
        print("[OK] Connected to Local PostgreSQL!")
    except Exception as e:
        print(f"[ERR] Failed to connect to Local PostgreSQL: {e}")
        await src_conn.close()
        return

    print("\nStarting table synchronization...")
    total_synced = 0
    try:
        for tbl in tables:
            synced = await sync_table(src_conn, dest_conn, tbl)
            total_synced += synced
        print("\nResetting ID sequences...")
        await reset_sequences(dest_conn)
    finally:
        await src_conn.close()
        await dest_conn.close()

    print("----------------------------------------------------------")
    print(f"[SUCCESS] All done! Total {total_synced} rows synced to Local PostgreSQL.")
    print("==========================================================")


if __name__ == "__main__":
    asyncio.run(main())
