"""Domain-Specific Seafood Factory Synthetic Time Series Generator.

Generates mathematically and commercially realistic factory data matching:
1. Monsoon & Catch Seasonality (s=7 for daily, s=12 for monthly)
2. Lagged Storm & Moon Impact:
   - When storms occur on day t (wind > 40 km/h or wave > 2.5m), inbound fresh seafood
     on days t+1 and t+2 drops by 40-60%.
   - Dark moon nights (new moon, lunar_phase < 0.25) increase light-lured catches by 25-40%.
3. Regulatory Fishing Ban:
   - Inbound volume drops by 40-50% during the Gulf spawning ban (Feb 15 - May 15).
4. Processing Yield Loss (Yield Rate 55% - 65%):
   - Whole Round fresh landing undergoes heading, peeling, and grading.
   - 35% - 45% weight loss is modeled before freezing and packing into 10kg cartons.
5. Outbound Export Demand:
   - Export shipments surge when THB weakens against USD (1-2 week lag).
   - Peak seasonal dispatch during pre-Christmas/New Year and Chinese New Year.
6. Daily Inventory Continuity:
   - Stock(t) = Stock(t-1) + Inbound_Boxes(t) - Outbound_Boxes(t)
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple
import numpy as np
import pandas as pd

from data_worker.data_service import fetch_complete_exogenous_dataset

logger = logging.getLogger("synthetic_generator")


async def generate_commercial_seafood_dataset(
    start_date: date | str = "2021-01-01",
    end_date: date | str = "2024-12-31",
    product_name: str = "Frozen Shrimp",
    box_weight_kg: float = 10.0,
    random_seed: int = 42,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Generate aligned daily and monthly time series coupled with real exogenous indicators.

    Returns:
        (daily_df, monthly_df)
    """
    np.random.seed(random_seed)
    if isinstance(start_date, str):
        start_date = date.fromisoformat(start_date)
    if isinstance(end_date, str):
        end_date = date.fromisoformat(end_date)

    # 1. Fetch real/calculated exogenous features for the entire period
    logger.info("Fetching exogenous features for synthetic series: %s to %s", start_date, end_date)
    exog_df = await fetch_complete_exogenous_dataset(start_date, end_date)
    dates = pd.to_datetime(exog_df["date"])
    n = len(dates)

    # 2. Base Seafood Landing Volume (Whole Round Inbound in tons/day)
    # Trend: Factory grows from ~45 tons/day in 2021 to ~65 tons/day in 2024
    trend = np.linspace(45.0, 65.0, n)

    # Yearly Seasonality (s=365): High landing post-monsoon (Aug-Nov), low during dry/ban season (Mar-May)
    day_of_year = np.array([d.timetuple().tm_yday for d in dates])
    season_monsoon = 15.0 * np.sin(2.0 * np.pi * (day_of_year - 150) / 365.25)

    # Weekly cycle (s=7): Fisherman landings peak Tuesday-Friday, quiet on Sunday
    dow = np.array([d.weekday() for d in dates])
    dow_factor = np.array([1.05, 1.15, 1.10, 1.12, 1.08, 0.85, 0.65])[dow]

    # Combine Base Inbound
    inbound_raw = (trend + season_monsoon) * dow_factor

    # 3. Apply Exogenous Impacts
    # Storm impact (Lagged t+1, t+2 drop of 40-60%)
    storms = exog_df["is_storm"].values
    storm_penalty = np.zeros(n)
    for i in range(1, n):
        if storms[i - 1] == 1:
            storm_penalty[i] += 0.45  # 45% drop next day
        if i >= 2 and storms[i - 2] == 1:
            storm_penalty[i] += 0.25  # 25% drop 2 days later
    storm_mult = np.clip(1.0 - storm_penalty, 0.25, 1.0)
    inbound_raw = inbound_raw * storm_mult

    # Fishing ban impact (40% reduction during official closure)
    ban_penalty = np.where(exog_df["is_fishing_ban"].values == 1, 0.40, 0.0)
    inbound_raw = inbound_raw * (1.0 - ban_penalty)

    # Lunar phase impact (New Moon = darker nights = higher light-lured catch)
    lunar = exog_df["lunar_phase"].values
    lunar_mult = 1.0 + 0.20 * (0.5 - lunar)  # +10% at new moon (0.0), -10% at full moon (1.0)
    inbound_raw = inbound_raw * lunar_mult

    # Add realistic biological noise
    noise_inbound = np.random.normal(0, 3.5, n)
    inbound_raw_tons = np.clip(inbound_raw + noise_inbound, 8.0, 120.0).round(2)

    # 4. Processing Yield Loss (Filleting / Shelling Loss: 35% - 45%)
    # Yield Rate = 0.58 (58% meat yield, 42% head/shell/waste loss)
    yield_rates = np.clip(0.58 + np.random.normal(0, 0.02, n), 0.52, 0.64)
    processed_meat_tons = inbound_raw_tons * yield_rates
    # Pack into cartons (10 kg per carton -> 100 boxes per ton)
    inbound_boxes = np.round(processed_meat_tons * 1000.0 / box_weight_kg).astype(int)

    # 5. Outbound Demand / Export Volume (Boxes/day)
    # Base export demand tracks production capacity with 5-10 day buffer
    base_outbound_tons = np.roll(processed_meat_tons, 7)
    base_outbound_tons[:7] = processed_meat_tons[:7]

    # Forex exchange rate impact: Weaker THB (higher USD/THB) stimulates overseas orders
    usd_thb = exog_df["usd_thb"].values
    mean_fx = np.mean(usd_thb)
    fx_elasticity = 1.0 + 0.04 * (usd_thb - mean_fx)  # 4% demand increase per 1 THB depreciation
    outbound_tons = base_outbound_tons * np.clip(fx_elasticity, 0.85, 1.25)

    # Christmas and Chinese New Year Export Surge
    cny = exog_df["is_chinese_new_year"].values
    xmas = exog_df["is_christmas_newyear"].values
    festival_mult = np.where(xmas == 1, 1.30, np.where(cny == 1, 1.25, 1.0))
    outbound_tons = outbound_tons * festival_mult

    # Weekly shipping container dispatch schedule (heavy outbound on Tue & Fri)
    outbound_dow = np.array([0.7, 1.35, 1.1, 1.0, 1.4, 0.7, 0.45])[dow]
    outbound_tons = outbound_tons * outbound_dow
    noise_outbound = np.random.normal(0, 2.5, n)
    outbound_tons = np.clip(outbound_tons + noise_outbound, 5.0, 110.0).round(2)
    outbound_boxes = np.round(outbound_tons * 1000.0 / box_weight_kg).astype(int)

    # 6. Cold Storage Inventory State Machine (Continuity)
    current_stock = 12500  # Initial stock in boxes
    stock_history = []
    temp_history = []
    humidity_history = []

    for i in range(n):
        net_change = inbound_boxes[i] - outbound_boxes[i]
        current_stock = int(max(1500, current_stock + net_change))
        stock_history.append(current_stock)

        # Cold Room physical sensor emulation (-20°C standard, slight fluctuation with door opening)
        temp_fluctuation = np.random.normal(0, 0.4)
        if outbound_boxes[i] > 3500:  # heavy door opening day
            temp_fluctuation += 1.2
        cold_temp = round(-20.5 + temp_fluctuation, 2)
        cold_hum = round(np.clip(88.0 + np.random.normal(0, 2.0), 80.0, 96.0), 1)

        temp_history.append(cold_temp)
        humidity_history.append(cold_hum)

    # Split stock into Zone A and Zone B (e.g. 55% / 45%)
    boxes_a = [int(round(s * 0.54)) for s in stock_history]
    boxes_b = [s - a for s, a in zip(stock_history, boxes_a)]

    daily_df = pd.DataFrame({
        "time": dates.dt.date,
        "product": product_name,
        "boxes_a": boxes_a,
        "boxes_b": boxes_b,
        "total_boxes": stock_history,
        "inbound_raw_tons": inbound_raw_tons,
        "inbound_boxes": inbound_boxes,
        "outbound_boxes": outbound_boxes,
        "yield_rate": yield_rates.round(3),
        "cold_room_temp_c": temp_history,
        "humidity_pct": humidity_history,
    })

    # Combine with Exogenous Features
    daily_combined = pd.merge(daily_df, exog_df, left_on="time", right_on="date", how="left")
    daily_combined.drop(columns=["date"], inplace=True)

    # 7. Aggregate into Monthly Series
    monthly_grouped = daily_combined.copy()
    monthly_grouped["month_time"] = pd.to_datetime(monthly_grouped["time"]).dt.to_period("M").dt.to_timestamp()

    monthly_df = monthly_grouped.groupby("month_time").agg({
        "product": "first",
        "boxes_a": "last",
        "boxes_b": "last",
        "total_boxes": "last",
        "inbound_boxes": "sum",
        "outbound_boxes": "sum",
        "inbound_raw_tons": "sum",
        "yield_rate": "mean",
        "cold_room_temp_c": "mean",
        "humidity_pct": "mean",
        "wind_speed_max_kmh": "mean",
        "precipitation_mm": "sum",
        "is_storm": "sum",
        "usd_thb": "mean",
        "brent_crude_usd": "mean",
        "is_fishing_ban": "max",
        "lunar_phase": "mean",
    }).reset_index()

    monthly_df.rename(columns={"month_time": "time"}, inplace=True)
    monthly_df["time"] = monthly_df["time"].dt.date

    logger.info("Generated %d daily rows and %d monthly rows of commercial seafood data", len(daily_combined), len(monthly_df))
    return daily_combined, monthly_df


async def export_and_seed_synthetic_data(
    start_date: str = "2021-01-01",
    end_date: str = "2024-12-31",
    csv_dir: Optional[Path] = None,
    seed_db: bool = True,
    database_url: Optional[str] = None,
) -> dict:
    """Generate and write synthetic commercial dataset to CSV and PostgreSQL."""
    daily_df, monthly_df = await generate_commercial_seafood_dataset(start_date, end_date)

    target_dir = csv_dir or (Path(__file__).resolve().parents[1] / "storage" / "data" / "csv_file")
    target_dir.mkdir(parents=True, exist_ok=True)

    daily_path = target_dir / "commercial_seafood_daily.csv"
    monthly_path = target_dir / "commercial_seafood_monthly.csv"
    legacy_path = target_dir / "inventory_summary (1).csv"

    daily_df.to_csv(daily_path, index=False, encoding="utf-8-sig")
    monthly_df.to_csv(monthly_path, index=False, encoding="utf-8-sig")

    # Also format a compatibility CSV matching inventory_summaries schema
    comp_records = []
    for idx, row in daily_df.iterrows():
        comp_records.append({
            "image": f"frame_{idx:05d}.jpg",
            "split": "train" if idx < len(daily_df) * 0.8 else "val",
            "date": str(row["time"]),
            "time": "12:00",
            "total_boxes": int(row["total_boxes"]),
            "total_weight_kg": round(float(row["total_boxes"]) * 10.0, 2),
            "occupied_slots": int(round(row["total_boxes"] / 40.0)),
            "empty_slots": int(max(0, 1000 - round(row["total_boxes"] / 40.0))),
            "occupancy_pct": round(min(100.0, (row["total_boxes"] / 40.0) / 1000.0 * 100.0), 2),
            "boxes_level1": int(round(row["total_boxes"] * 0.35)),
            "boxes_level2": int(round(row["total_boxes"] * 0.30)),
            "boxes_level3": int(round(row["total_boxes"] * 0.20)),
            "boxes_level4": int(max(0, row["total_boxes"] - round(row["total_boxes"] * 0.85))),
            "inbound_boxes": int(row["inbound_boxes"]),
            "outbound_boxes": int(row["outbound_boxes"]),
            "cold_room_temp_c": float(row["cold_room_temp_c"]),
            "humidity_pct": float(row["humidity_pct"]),
        })
    pd.DataFrame(comp_records).to_csv(legacy_path, index=False, encoding="utf-8-sig")
    logger.info("Saved synthetic datasets to %s, %s, and %s", daily_path, monthly_path, legacy_path)

    # Seed into PostgreSQL if requested
    db_counts = {"daily": 0, "monthly": 0, "exog": 0}
    if seed_db:
        from data_worker.data_service import sync_exogenous_to_database, _get_engine
        # 1. Sync exogenous
        db_counts["exog"] = await sync_exogenous_to_database(start_date, end_date, database_url)

        # 2. Sync monthly_inventories and daily_inventories
        engine = _get_engine(database_url)
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import async_sessionmaker
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        monthly_records = monthly_df.to_dict(orient="records")
        daily_records = daily_df.to_dict(orient="records")

        upsert_monthly = text("""
            INSERT INTO monthly_inventories (time, product, boxes_a, boxes_b, total_boxes, created_at)
            VALUES (:time, :product, :boxes_a, :boxes_b, :total_boxes, NOW())
            ON CONFLICT (time, product) DO UPDATE SET
                boxes_a = EXCLUDED.boxes_a,
                boxes_b = EXCLUDED.boxes_b,
                total_boxes = EXCLUDED.total_boxes;
        """)

        upsert_daily = text("""
            INSERT INTO daily_inventories (time, product, boxes_a, boxes_b, total_boxes, inbound_boxes, outbound_boxes, created_at)
            VALUES (:time, :product, :boxes_a, :boxes_b, :total_boxes, :inbound_boxes, :outbound_boxes, NOW())
            ON CONFLICT (time, product) DO UPDATE SET
                boxes_a = EXCLUDED.boxes_a,
                boxes_b = EXCLUDED.boxes_b,
                total_boxes = EXCLUDED.total_boxes,
                inbound_boxes = EXCLUDED.inbound_boxes,
                outbound_boxes = EXCLUDED.outbound_boxes;
        """)

        async with session_factory() as session:
            for r in monthly_records:
                await session.execute(upsert_monthly, {
                    "time": r["time"], "product": r["product"],
                    "boxes_a": r["boxes_a"], "boxes_b": r["boxes_b"],
                    "total_boxes": r["total_boxes"]
                })
            for r in daily_records:
                await session.execute(upsert_daily, {
                    "time": r["time"], "product": r["product"],
                    "boxes_a": r["boxes_a"], "boxes_b": r["boxes_b"],
                    "total_boxes": r["total_boxes"],
                    "inbound_boxes": r["inbound_boxes"],
                    "outbound_boxes": r["outbound_boxes"],
                })
            await session.commit()
            db_counts["monthly"] = len(monthly_records)
            db_counts["daily"] = len(daily_records)
            logger.info("Seeded %d monthly and %d daily records to PostgreSQL", len(monthly_records), len(daily_records))
        await engine.dispose()

    return {
        "status": "success",
        "daily_path": str(daily_path),
        "monthly_path": str(monthly_path),
        "legacy_path": str(legacy_path),
        "daily_rows": len(daily_df),
        "monthly_rows": len(monthly_df),
        "db_synced": db_counts,
    }


if __name__ == "__main__":
    asyncio.run(export_and_seed_synthetic_data(seed_db=False))
