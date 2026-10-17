"""Forex, Commodity, and Seafood Equity Market Data Fetcher.

Fetches real financial market indicators impacting seafood exports and supply costs:
- USD/THB (Main export currency)
- JPY/THB (Key Asian export market)
- EUR/THB (European export market)
- Brent Crude (BZ=F) (Proxy for vessel diesel & reefer container freight cost)
- TU.BK (Thai Union Group - industry bellwether)
- ASIAN.BK (Asian Seafoods Coldstorage)
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
import numpy as np
import pandas as pd

logger = logging.getLogger("data_worker.forex")


def fetch_financial_market_data(
    start_date: date | str,
    end_date: date | str,
) -> pd.DataFrame:
    """Fetch daily forex exchange rates, oil price, and seafood stocks via yfinance.

    Handles weekends/holidays with forward-fill, and falls back to realistic
    Thai macroeconomic ranges if network or Yahoo Finance is unavailable.
    """
    if isinstance(start_date, str):
        start_date = date.fromisoformat(start_date)
    if isinstance(end_date, str):
        end_date = date.fromisoformat(end_date)

    dates = pd.date_range(start_date, end_date, freq="D")
    df_result = pd.DataFrame({"date": dates.date})

    try:
        import yfinance as yf

        symbols_map = {
            "THB=X": "usd_thb",
            "JPYTHB=X": "jpy_thb",
            "EURTHB=X": "eur_thb",
            "BZ=F": "brent_crude_usd",
            "TU.BK": "tu_bk_close",
            "ASIAN.BK": "asian_bk_close",
        }

        # Query yfinance (give 3 extra buffer days before start)
        buffer_start = start_date - timedelta(days=5)
        raw_data = yf.download(
            tickers=list(symbols_map.keys()),
            start=buffer_start.isoformat(),
            end=(end_date + timedelta(days=2)).isoformat(),
            progress=False,
            auto_adjust=True,
        )

        if not raw_data.empty:
            closes = raw_data["Close"] if "Close" in raw_data else raw_data
            parsed = pd.DataFrame()
            parsed["date"] = pd.to_datetime(closes.index).date

            for symbol, col_name in symbols_map.items():
                if symbol in closes.columns:
                    parsed[col_name] = closes[symbol].values

            # Forward-fill weekends & market holidays, then merge onto calendar dates
            parsed = parsed.ffill().bfill()
            df_result = pd.merge(df_result, parsed, on="date", how="left")
            logger.info("Successfully fetched financial tickers from Yahoo Finance")

    except Exception as exc:
        logger.warning("yfinance fetch encountered warning (%s). Employing macroeconomic baseline.", exc)

    n = len(df_result)
    # Fill missing values with realistic macroeconomic baseline values for Thailand
    if "usd_thb" not in df_result or df_result["usd_thb"].isna().all():
        # Baseline around 34.0 - 36.5 THB per USD with gentle random walk
        walk = np.cumsum(np.random.normal(0, 0.04, n))
        df_result["usd_thb"] = np.clip(34.8 + walk, 32.0, 37.5).round(3)
    else:
        df_result["usd_thb"] = df_result["usd_thb"].ffill().bfill().fillna(35.0).round(3)

    if "jpy_thb" not in df_result or df_result["jpy_thb"].isna().all():
        df_result["jpy_thb"] = (df_result["usd_thb"] / 152.0).round(4)
    else:
        df_result["jpy_thb"] = df_result["jpy_thb"].ffill().bfill().fillna(0.23).round(4)

    if "eur_thb" not in df_result or df_result["eur_thb"].isna().all():
        df_result["eur_thb"] = (df_result["usd_thb"] * 1.08).round(3)
    else:
        df_result["eur_thb"] = df_result["eur_thb"].ffill().bfill().fillna(38.0).round(3)

    if "brent_crude_usd" not in df_result or df_result["brent_crude_usd"].isna().all():
        oil_walk = np.cumsum(np.random.normal(0, 0.35, n))
        df_result["brent_crude_usd"] = np.clip(80.0 + oil_walk, 65.0, 110.0).round(2)
    else:
        df_result["brent_crude_usd"] = df_result["brent_crude_usd"].ffill().bfill().fillna(78.5).round(2)

    if "tu_bk_close" not in df_result or df_result["tu_bk_close"].isna().all():
        tu_walk = np.cumsum(np.random.normal(0, 0.1, n))
        df_result["tu_bk_close"] = np.clip(14.5 + tu_walk, 11.0, 20.0).round(2)
    else:
        df_result["tu_bk_close"] = df_result["tu_bk_close"].ffill().bfill().fillna(14.5).round(2)

    if "asian_bk_close" not in df_result or df_result["asian_bk_close"].isna().all():
        asian_walk = np.cumsum(np.random.normal(0, 0.08, n))
        df_result["asian_bk_close"] = np.clip(7.8 + asian_walk, 5.5, 12.0).round(2)
    else:
        df_result["asian_bk_close"] = df_result["asian_bk_close"].ffill().bfill().fillna(7.8).round(2)

    return df_result
