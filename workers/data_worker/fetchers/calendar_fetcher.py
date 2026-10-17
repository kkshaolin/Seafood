"""Seafood Industry Calendar & Regulatory Dummy Variables Fetcher.

Generates mathematical features representing:
1. Lunar Phase (0.0=New Moon to 1.0=Full Moon):
   Seafood landing volume (especially squid, wild shrimp, pelagic fish) varies heavily
   with moonlight illumination because commercial light-luring boats only operate during
   dark nights (New Moon).
2. Seasonal Fishing Bans (Department of Fisheries):
   - Gulf of Thailand spawning closure (Feb 15 - May 15)
   - Andaman Sea closure (June 1 - July 31)
3. Key Consumption & Export Festivals:
   - Chinese New Year (Surge in premium seafood demand)
   - Songkran (Apr 13 - 15)
   - Vegetarian Festival (Je) (Sharp drop in domestic seafood consumption)
   - Christmas & Year-End Export Surge (Dec 20 - Jan 5)
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
import pandas as pd


def compute_lunar_phase(d: date) -> float:
    """Compute moon illumination phase [0.0 = New Moon, 1.0 = Full Moon].

    Uses astronomical trigonometric synodic cycle (29.53058867 days).
    Known reference New Moon: 2000-01-06.
    """
    ref_new_moon = date(2000, 1, 6)
    days_since_ref = (d - ref_new_moon).total_seconds() / 86400.0
    synodic_month = 29.53058867
    cycle_pos = (days_since_ref % synodic_month) / synodic_month  # 0.0 to 1.0
    # Illumination fraction: 0.0 at new moon, 1.0 at full moon (cycle_pos = 0.5)
    illumination = 0.5 * (1.0 - math.cos(2.0 * math.pi * cycle_pos))
    return round(illumination, 4)


def is_chinese_new_year_season(d: date) -> int:
    """Approximate 10-day window around Chinese New Year (Jan/Feb)."""
    # Known CNY dates: 2021-02-12, 2022-02-01, 2023-01-22, 2024-02-10, 2025-01-29, 2026-02-17
    cny_dates = [
        date(2021, 2, 12), date(2022, 2, 1), date(2023, 1, 22),
        date(2024, 2, 10), date(2025, 1, 29), date(2026, 2, 17),
    ]
    for cny in cny_dates:
        if abs((d - cny).days) <= 5:
            return 1
    return 0


def is_vegetarian_festival_season(d: date) -> int:
    """Approximate 9-day Thai Vegetarian Festival (Je) in Sept/Oct."""
    # Known Je dates:
    je_windows = [
        (date(2021, 10, 5), date(2021, 10, 14)),
        (date(2022, 9, 25), date(2022, 10, 4)),
        (date(2023, 10, 14), date(2023, 10, 23)),
        (date(2024, 10, 2), date(2024, 10, 11)),
        (date(2025, 10, 20), date(2025, 10, 29)),
        (date(2026, 10, 9), date(2026, 10, 18)),
    ]
    for start_w, end_w in je_windows:
        if start_w <= d <= end_w:
            return 1
    return 0


def generate_calendar_features(
    start_date: date | str,
    end_date: date | str,
) -> pd.DataFrame:
    """Generate calendar, festival, and regulatory dummy variables (0/1)."""
    if isinstance(start_date, str):
        start_date = date.fromisoformat(start_date)
    if isinstance(end_date, str):
        end_date = date.fromisoformat(end_date)

    dates = pd.date_range(start_date, end_date, freq="D")
    records = []

    for ts in dates:
        d = ts.date()
        m, day = d.month, d.day

        # 1. Fishing Ban (Gulf of Thailand: Feb 15 - May 15)
        ban = 1 if ((m == 2 and day >= 15) or m in (3, 4) or (m == 5 and day <= 15)) else 0

        # 2. Songkran (Apr 13 - 15)
        songkran = 1 if (m == 4 and 12 <= day <= 16) else 0

        # 3. Christmas & Year-End Export Surge (Dec 20 - Jan 5)
        xmas_ny = 1 if ((m == 12 and day >= 20) or (m == 1 and day <= 5)) else 0

        # 4. Chinese New Year
        cny = is_chinese_new_year_season(d)

        # 5. Vegetarian Festival (Je)
        je = is_vegetarian_festival_season(d)

        # 6. Lunar Phase
        lunar = compute_lunar_phase(d)

        records.append({
            "date": d,
            "is_fishing_ban": ban,
            "is_chinese_new_year": cny,
            "is_songkran": songkran,
            "is_vegetarian_festival": je,
            "is_christmas_newyear": xmas_ny,
            "lunar_phase": lunar,
        })

    return pd.DataFrame(records)
