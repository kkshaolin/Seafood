"""Exogenous Data Service: coordinates fetchers, database cache, and SARIMAX alignment.

Provides:
- Ingestion pipeline from Open-Meteo, yfinance, and calendar regulators
- PostgreSQL caching into 'exogenous_daily' table
- Feature transformation for daily and monthly SARIMAX exogenous matrices
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any
import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from data_worker.fetchers.weather_fetcher import fetch_marine_and_weather_data
from data_worker.fetchers.forex_fetcher import fetch_financial_market_data
from data_worker.fetchers.calendar_fetcher import generate_calendar_features

logger = logging.getLogger("data_worker.service")


def _get_engine(database_url: Optional[str] = None):
    url = database_url or os.getenv(
        "DATABASE_URL", "postgresql://admin:secretpassword@postgres:5432/my_database"
    )
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return create_async_engine(url, poolclass=NullPool)


async def fetch_complete_exogenous_dataset(
    start_date: date | str,
    end_date: date | str,
) -> pd.DataFrame:
    """Fetch and merge Weather, Forex, and Calendar features into a single daily DataFrame."""
    if isinstance(start_date, str):
        start_date = date.fromisoformat(start_date)
    if isinstance(end_date, str):
        end_date = date.fromisoformat(end_date)

    logger.info("Fetching complete exogenous features from %s to %s", start_date, end_date)

    # 1. Fetch weather (async)
    weather_task = fetch_marine_and_weather_data(start_date, end_date)
    # 2. Fetch forex (run sync in thread pool)
    loop = asyncio.get_running_loop()
    forex_task = loop.run_in_executor(None, fetch_financial_market_data, start_date, end_date)
    # 3. Generate calendar
    calendar_task = loop.run_in_executor(None, generate_calendar_features, start_date, end_date)

    weather_df, forex_df, cal_df = await asyncio.gather(weather_task, forex_task, calendar_task)

    # Merge on 'date'
    merged = pd.merge(weather_df, forex_df, on="date", how="outer")
    merged = pd.merge(merged, cal_df, on="date", how="outer")
    merged["date"] = pd.to_datetime(merged["date"]).dt.date
    merged = merged.sort_values("date").reset_index(drop=True)

    # Forward fill then backward fill any gaps
    merged = merged.ffill().bfill()
    return merged


async def sync_exogenous_to_database(
    start_date: date | str,
    end_date: date | str,
    database_url: Optional[str] = None,
) -> int:
    """Upsert daily exogenous records into PostgreSQL 'exogenous_daily'."""
    df = await fetch_complete_exogenous_dataset(start_date, end_date)
    if df.empty:
        return 0

    engine = _get_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    upsert_sql = text("""
        INSERT INTO exogenous_daily (
            date, wind_speed_max_kmh, precipitation_mm, sea_surface_temp_c, wave_height_m, is_storm,
            usd_thb, jpy_thb, eur_thb, brent_crude_usd, tu_bk_close, asian_bk_close,
            is_fishing_ban, is_chinese_new_year, is_songkran, is_vegetarian_festival,
            is_christmas_newyear, lunar_phase, source, created_at
        ) VALUES (
            :date, :wind_speed_max_kmh, :precipitation_mm, :sea_surface_temp_c, :wave_height_m, :is_storm,
            :usd_thb, :jpy_thb, :eur_thb, :brent_crude_usd, :tu_bk_close, :asian_bk_close,
            :is_fishing_ban, :is_chinese_new_year, :is_songkran, :is_vegetarian_festival,
            :is_christmas_newyear, :lunar_phase, :source, NOW()
        )
        ON CONFLICT (date) DO UPDATE SET
            wind_speed_max_kmh = EXCLUDED.wind_speed_max_kmh,
            precipitation_mm = EXCLUDED.precipitation_mm,
            sea_surface_temp_c = EXCLUDED.sea_surface_temp_c,
            wave_height_m = EXCLUDED.wave_height_m,
            is_storm = EXCLUDED.is_storm,
            usd_thb = EXCLUDED.usd_thb,
            jpy_thb = EXCLUDED.jpy_thb,
            eur_thb = EXCLUDED.eur_thb,
            brent_crude_usd = EXCLUDED.brent_crude_usd,
            tu_bk_close = EXCLUDED.tu_bk_close,
            asian_bk_close = EXCLUDED.asian_bk_close,
            is_fishing_ban = EXCLUDED.is_fishing_ban,
            is_chinese_new_year = EXCLUDED.is_chinese_new_year,
            is_songkran = EXCLUDED.is_songkran,
            is_vegetarian_festival = EXCLUDED.is_vegetarian_festival,
            is_christmas_newyear = EXCLUDED.is_christmas_newyear,
            lunar_phase = EXCLUDED.lunar_phase,
            source = EXCLUDED.source;
    """)

    records = df.to_dict(orient="records")
    for r in records:
        r["source"] = "open-meteo+yfinance"

    try:
        async with session_factory() as session:
            await session.execute(upsert_sql, records)
            await session.commit()
            logger.info("Synced %d daily exogenous records to database", len(records))
    finally:
        await engine.dispose()

    return len(records)


async def get_exogenous_matrix(
    start_date: date | str,
    end_date: date | str,
    freq: str = "MS",
    database_url: Optional[str] = None,
) -> pd.DataFrame:
    """Retrieve aligned exogenous matrix for SARIMAX.

    Args:
        start_date: Start date
        end_date: End date
        freq: 'D' for daily models, 'MS' for monthly models
    """
    if isinstance(start_date, str):
        start_date = date.fromisoformat(start_date)
    if isinstance(end_date, str):
        end_date = date.fromisoformat(end_date)

    # 1. Try reading from PostgreSQL
    df = pd.DataFrame()
    try:
        engine = _get_engine(database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        query = text("""
            SELECT date, wind_speed_max_kmh, precipitation_mm, sea_surface_temp_c, wave_height_m, is_storm,
                   usd_thb, jpy_thb, eur_thb, brent_crude_usd, tu_bk_close, asian_bk_close,
                   is_fishing_ban, is_chinese_new_year, is_songkran, is_vegetarian_festival,
                   is_christmas_newyear, lunar_phase
            FROM exogenous_daily
            WHERE date >= :s AND date <= :e
            ORDER BY date ASC
        """)
        async with session_factory() as session:
            res = await session.execute(query, {"s": start_date, "e": end_date})
            rows = res.fetchall()
            if rows:
                df = pd.DataFrame(rows, columns=res.keys())
        await engine.dispose()
    except Exception as exc:
        logger.debug("Database query for exogenous data failed (%s); will fetch directly", exc)

    # 2. If DB lacks data, fetch directly
    if df.empty or len(df) < (end_date - start_date).days * 0.8:
        df = await fetch_complete_exogenous_dataset(start_date, end_date)

    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()

    if freq == "MS":
        # Monthly Resample logic:
        # Sum counts/precipitation, mean rates/temperatures
        agg_rules = {
            "wind_speed_max_kmh": "mean",
            "precipitation_mm": "sum",
            "sea_surface_temp_c": "mean",
            "wave_height_m": "mean",
            "is_storm": "sum",
            "usd_thb": "mean",
            "jpy_thb": "mean",
            "eur_thb": "mean",
            "brent_crude_usd": "mean",
            "tu_bk_close": "mean",
            "asian_bk_close": "mean",
            "is_fishing_ban": "max",
            "is_chinese_new_year": "max",
            "is_songkran": "max",
            "is_vegetarian_festival": "max",
            "is_christmas_newyear": "max",
            "lunar_phase": "mean",
        }
        monthly_df = df.resample("MS").agg(agg_rules).ffill().bfill()
        return monthly_df

    return df
