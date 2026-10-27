"""Simple day-ahead baselines (kW per 15-min slot)."""

from __future__ import annotations

import pandas as pd

from b2g.forecasting.features import lag_days


def persistence(actual: pd.Series) -> pd.Series:
    """'Same as yesterday': each slot of day d gets the actual value of that slot on day d-1."""
    return lag_days(actual, 1)


def same_day_last_week(actual: pd.Series) -> pd.Series:
    """Each slot of day d gets the actual value of that slot on day d-7 (captures weekday/weekend)."""
    return lag_days(actual, 7)


def pv_physics(df: pd.DataFrame) -> pd.Series:
    """PV from the day-ahead weather forecast via the M2 formula (P = kWp x GHI_forecast/1000 x derate)."""
    return df["pv_forecast_kw"]
