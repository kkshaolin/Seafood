"""Unit and Integration Tests for SARIMAX, Exogenous Data, and Commercial Pipeline."""
import pytest
import sys
from pathlib import Path
from datetime import date

workspace_root = Path(__file__).resolve().parents[1]
backend_src = workspace_root / "backend" / "src"
workers_dir = workspace_root / "workers"

for p in [str(backend_src), str(workers_dir), str(workspace_root)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np
import pandas as pd

from data_worker.fetchers.calendar_fetcher import compute_lunar_phase, generate_calendar_features
from data_worker.fetchers.weather_fetcher import fetch_marine_and_weather_data
from data_worker.fetchers.forex_fetcher import fetch_financial_market_data
from data_worker.data_service import fetch_complete_exogenous_dataset
from synthetic_data_generator import generate_commercial_seafood_dataset
from inference_worker.forecast_model.arima import (
    train_sarimax, forecast_sarimax, select_optimal_sarimax_order,
    extract_sarimax_feature_importance,
)
from forecasting.schemas import (
    ForecastRequest, ForecastResponse, WhatIfSimulateRequest, WhatIfSimulateResponse,
)


def test_lunar_phase_bounds():
    """Lunar phase must remain strictly between 0.0 and 1.0."""
    for d in [date(2024, 1, 1), date(2024, 1, 15), date(2024, 7, 20), date(2024, 12, 31)]:
        phase = compute_lunar_phase(d)
        assert 0.0 <= phase <= 1.0


def test_calendar_features_generation():
    """Verify fishing ban, holidays, and lunar phase are populated."""
    df = generate_calendar_features("2024-03-01", "2024-03-10")
    assert len(df) == 10
    # March is within the Gulf fishing ban (Feb 15 - May 15)
    assert (df["is_fishing_ban"] == 1).all()
    assert "lunar_phase" in df.columns


@pytest.mark.asyncio
async def test_exogenous_complete_pipeline():
    """Verify merged exogenous features contains weather, forex, and calendar features."""
    df = await fetch_complete_exogenous_dataset("2024-01-01", "2024-01-07")
    assert len(df) == 7
    expected_cols = [
        "date", "wind_speed_max_kmh", "is_storm", "usd_thb",
        "brent_crude_usd", "is_fishing_ban", "lunar_phase",
    ]
    for c in expected_cols:
        assert c in df.columns
    # Check no NaNs
    assert not df[expected_cols].isna().any().any()


@pytest.mark.asyncio
async def test_synthetic_commercial_dataset():
    """Verify commercial dataset models yield loss, storm lags, and stock continuity."""
    daily_df, monthly_df = await generate_commercial_seafood_dataset("2023-01-01", "2023-03-31")
    assert len(daily_df) == 90
    assert len(monthly_df) == 3

    # Yield rate must reflect processing loss (52% - 65% meat yield)
    assert (daily_df["yield_rate"] >= 0.50).all()
    assert (daily_df["yield_rate"] <= 0.68).all()

    # Stock continuity check
    assert (daily_df["total_boxes"] > 0).all()
    assert (daily_df["inbound_boxes"] >= 0).all()
    assert (daily_df["outbound_boxes"] >= 0).all()


def test_sarimax_training_and_feature_importance():
    """Test SARIMAX model fitting with seasonal order and exogenous coefficients."""
    # Create synthetic monthly test series (24 months)
    dates = pd.date_range("2022-01-01", periods=24, freq="MS")
    y = np.linspace(1000, 1500, 24) + 150 * np.sin(np.linspace(0, 4 * np.pi, 24))
    exog1 = np.random.normal(35, 1, 24)  # e.g. usd_thb
    exog2 = np.random.binomial(1, 0.2, 24)  # e.g. storm

    df = pd.DataFrame({"y": y, "usd_thb": exog1, "is_storm": exog2}, index=dates)

    # Train SARIMAX (1,1,0)(1,0,0,12)
    fitted = train_sarimax(
        df, target_col="y", exog_cols=["usd_thb", "is_storm"],
        p=1, d=1, q=0, P=1, D=0, Q=0, s=12
    )
    assert fitted is not None

    # Forecast 3 steps
    future_exog = pd.DataFrame({
        "usd_thb": [35.2, 35.5, 35.8],
        "is_storm": [0, 1, 0],
    }, index=pd.date_range("2024-01-01", periods=3, freq="MS"))

    preds, conf_int = forecast_sarimax(fitted, steps=3, future_exog=future_exog)
    assert len(preds) == 3
    assert len(conf_int) == 3

    # Feature importance extraction
    importance = extract_sarimax_feature_importance(fitted, ["usd_thb", "is_storm"])
    assert len(importance) == 2
    assert "coefficient" in importance[0]


def test_whatif_request_schema_validation():
    """Validate WhatIfSimulateRequest and Response schemas."""
    req = WhatIfSimulateRequest(
        product="Frozen Shrimp",
        forecast_horizon=6,
        storm_days=3,
        fx_change_pct=5.0,
        price_per_kg_thb=220.0,
    )
    assert req.product == "Frozen Shrimp"
    assert req.storm_days == 3
    assert req.fx_change_pct == 5.0
