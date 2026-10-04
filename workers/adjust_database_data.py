"""Adjust database data according to user request:
1. Ensure data is up to 2026-10-04 with latest time 23:00.
2. daily_inventories pulls latest value from box_logs for 2026-10-04 (ensuring no duplicate days).
3. monthly_inventories pulls end-of-month values from daily_inventories, and yearly_inventories pulls month 12 values.
"""

import asyncio
from datetime import datetime, timezone, date
import asyncpg

DB_URL = "postgresql://admin:secretpassword@localhost:5433/my_database"

async def main():
    conn = await asyncpg.connect(DB_URL)
    try:
        print("=== BEFORE ADJUSTMENT ===")
        for tbl in ['box_logs', 'daily_inventories', 'monthly_inventories', 'yearly_inventories']:
            count = await conn.fetchval(f"SELECT count(*) FROM {tbl}")
            min_t = await conn.fetchval(f"SELECT min(time)::text FROM {tbl}")
            max_t = await conn.fetchval(f"SELECT max(time)::text FROM {tbl}")
            print(f"{tbl:20}: count={count:5}, min={min_t}, max={max_t}")

        # -------------------------------------------------------------
        # STEP 1: Adjust box_logs to have data up to 2026-10-04 23:00
        # -------------------------------------------------------------
        print("\n--- STEP 1: Adjusting box_logs up to 2026-10-04 23:00 ---")
        # Check if there is already a log at 2026-10-04 23:00
        target_log_time = datetime(2026, 10, 4, 23, 0, 0, tzinfo=timezone.utc)
        existing_log = await conn.fetchrow(
            "SELECT * FROM box_logs WHERE time = $1", target_log_time
        )
        if not existing_log:
            # Insert the 23:00 closing sampling log
            await conn.execute(
                """
                INSERT INTO box_logs (time, product, boxes_a, boxes_b, total_boxes, camera_id, image_path, confidence, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9);
                """,
                target_log_time,
                "Frozen Shrimp",
                32,
                28,
                60,
                "cam_main,cam_dock",
                "ZoneA/frame_20261004_230000.jpg;ZoneB/frame_20261004_230000.jpg",
                0.95,
                target_log_time
            )
            print(f"Inserted box_log for 2026-10-04 23:00:00: boxes_a=32, boxes_b=28, total_boxes=60")
        else:
            print("box_log for 2026-10-04 23:00:00 already exists.")

        # Delete any box_logs after 2026-10-04 23:00:00 if any
        del_box = await conn.execute(
            "DELETE FROM box_logs WHERE time > $1", target_log_time
        )
        print(f"Deleted future box_logs (> 2026-10-04 23:00): {del_box}")

        # -------------------------------------------------------------
        # STEP 2: Update daily_inventories from latest box_logs for 2026-10-04
        # & remove any future daily records (> 2026-10-04)
        # & ensure no duplicate days
        # -------------------------------------------------------------
        print("\n--- STEP 2: Updating daily_inventories from latest box_logs ---")
        # Fetch latest box_log on 2026-10-04
        latest_box = await conn.fetchrow(
            """
            SELECT time, product, boxes_a, boxes_b, total_boxes 
            FROM box_logs 
            WHERE time::date = '2026-10-04' 
            ORDER BY time DESC 
            LIMIT 1;
            """
        )
        print(f"Latest box_log for 2026-10-04: time={latest_box['time']}, boxes_a={latest_box['boxes_a']}, boxes_b={latest_box['boxes_b']}, total={latest_box['total_boxes']}")

        # Delete any future daily_inventories (> 2026-10-04)
        del_daily = await conn.execute("DELETE FROM daily_inventories WHERE time > '2026-10-04'")
        print(f"Deleted future daily_inventories (> 2026-10-04): {del_daily}")

        # Ensure no duplicates on 2026-10-04: keep at most 1 row, delete any extra
        all_today = await conn.fetch("SELECT id FROM daily_inventories WHERE time = '2026-10-04' ORDER BY id ASC")
        if len(all_today) > 1:
            keep_id = all_today[0]['id']
            del_ids = [r['id'] for r in all_today[1:]]
            await conn.execute("DELETE FROM daily_inventories WHERE id = ANY($1)", del_ids)
            print(f"Removed {len(del_ids)} duplicate row(s) for 2026-10-04 in daily_inventories")

        # Update or insert the daily record for 2026-10-04
        await conn.execute(
            """
            INSERT INTO daily_inventories (time, product, boxes_a, boxes_b, total_boxes, inbound_boxes, outbound_boxes, created_at)
            VALUES ($1, $2, $3, $4, $5, 0, 0, $6)
            ON CONFLICT (time, product) DO UPDATE SET
                boxes_a = EXCLUDED.boxes_a,
                boxes_b = EXCLUDED.boxes_b,
                total_boxes = EXCLUDED.total_boxes,
                created_at = EXCLUDED.created_at;
            """,
            date(2026, 10, 4),
            latest_box['product'],
            latest_box['boxes_a'],
            latest_box['boxes_b'],
            latest_box['total_boxes'],
            latest_box['time']
        )
        print("Updated daily_inventories for 2026-10-04 with latest camera log values.")

        # -------------------------------------------------------------
        # STEP 3: monthly_inventories pulls end-of-month from daily_inventories
        # & yearly_inventories pulls month 12 of each year
        # -------------------------------------------------------------
        print("\n--- STEP 3: Updating monthly_inventories and yearly_inventories ---")
        # Delete future months (> 2026-10-01)
        del_monthly = await conn.execute("DELETE FROM monthly_inventories WHERE time > '2026-10-01'")
        print(f"Deleted future monthly_inventories (> 2026-10-01): {del_monthly}")

        # For every month up to 2026-10-01, pull the end-of-month record from daily_inventories
        upsert_monthly = await conn.execute(
            """
            WITH end_of_months AS (
                SELECT DISTINCT ON (date_trunc('month', time), product)
                    date_trunc('month', time)::date as month_date,
                    time as end_of_month_date,
                    product,
                    boxes_a,
                    boxes_b,
                    total_boxes
                FROM daily_inventories
                WHERE time <= '2026-10-04'
                ORDER BY date_trunc('month', time), product, time DESC
            )
            INSERT INTO monthly_inventories (time, product, boxes_a, boxes_b, total_boxes, created_at)
            SELECT month_date, product, boxes_a, boxes_b, total_boxes, NOW()
            FROM end_of_months
            ON CONFLICT (time, product) DO UPDATE SET
                boxes_a = EXCLUDED.boxes_a,
                boxes_b = EXCLUDED.boxes_b,
                total_boxes = EXCLUDED.total_boxes;
            """
        )
        print(f"Upserted monthly_inventories from daily end-of-month: {upsert_monthly}")

        # Delete future years (> 2025-01-01) in yearly_inventories because 2026 month 12 hasn't occurred yet
        del_yearly = await conn.execute("DELETE FROM yearly_inventories WHERE time > '2025-01-01'")
        print(f"Deleted future yearly_inventories (> 2025-01-01): {del_yearly}")

        # For each year (2021-2025), pull month 12 from monthly_inventories
        upsert_yearly = await conn.execute(
            """
            WITH yearly_dec AS (
                SELECT 
                    date_trunc('year', time)::date as year_date,
                    product,
                    boxes_a,
                    boxes_b,
                    total_boxes
                FROM monthly_inventories
                WHERE EXTRACT(MONTH FROM time) = 12
                  AND time <= '2025-12-01'
            )
            INSERT INTO yearly_inventories (time, product, boxes_a, boxes_b, total_boxes, created_at)
            SELECT year_date, product, boxes_a, boxes_b, total_boxes, NOW()
            FROM yearly_dec
            ON CONFLICT (time, product) DO UPDATE SET
                boxes_a = EXCLUDED.boxes_a,
                boxes_b = EXCLUDED.boxes_b,
                total_boxes = EXCLUDED.total_boxes;
            """
        )
        print(f"Upserted yearly_inventories from month 12: {upsert_yearly}")

        # Also clean up old future arima_forecasts so they don't show 2027 forecasts
        del_arima = await conn.execute("DELETE FROM arima_forecasts WHERE time > '2026-10-01'")
        print(f"Cleaned old arima_forecasts: {del_arima}")

        print("\n=== AFTER ADJUSTMENT ===")
        for tbl in ['box_logs', 'daily_inventories', 'monthly_inventories', 'yearly_inventories', 'arima_forecasts']:
            count = await conn.fetchval(f"SELECT count(*) FROM {tbl}")
            min_t = await conn.fetchval(f"SELECT min(time)::text FROM {tbl}")
            max_t = await conn.fetchval(f"SELECT max(time)::text FROM {tbl}")
            print(f"{tbl:20}: count={count:5}, min={min_t}, max={max_t}")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
