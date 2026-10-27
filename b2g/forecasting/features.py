"""Model inputs for a day-ahead forecast of day d, using only information available by the end of d-1.

Allowed: actual values (PV, load) up to day d-1, the day-ahead weather forecast for day d
(`*_forecast_*` columns from M2, issued ~24 h ahead), and the calendar. Never: actual weather or
actual PV/load of day d.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

SLOT_H = 0.25  # hours per 15-min slot

PV_FEATURES = [
    "slot", "doy_sin", "doy_cos",
    "ghi_forecast_wm2", "temp_forecast_c", "cloud_forecast_pct", "pv_forecast_kw",
    "ghi_forecast_day_kwh_m2", "cloud_forecast_day_pct",
    "pv_lag1_kw", "pv_lag1_day_kwh",
]
LOAD_FEATURES = [
    "slot", "day_of_week", "is_weekend", "doy_sin", "doy_cos", "temp_forecast_c",
    "load_lag1_kw", "load_lag7_kw", "load_lag1_day_kwh",
]


def lag_days(series: pd.Series, days: int) -> pd.Series:
    """Value of the same 15-min slot `days` days earlier; NaN where that day is not in the data."""
    shifted = series.copy()
    shifted.index = shifted.index + pd.Timedelta(days=days)
    return shifted.reindex(series.index)


def daily_total_lag(series: pd.Series, days: int, scale: float) -> pd.Series:
    """Daily sum x `scale` of the day `days` days earlier, repeated on every slot (e.g. kW -> kWh with 0.25)."""
    day = series.index.normalize()
    totals = series.groupby(day).sum() * scale
    totals.index = totals.index + pd.Timedelta(days=days)
    return pd.Series(totals.reindex(day).to_numpy(), index=series.index)


def same_day_mean(series: pd.Series) -> pd.Series:
    """Mean over the whole day, repeated on every slot (only for day-ahead FORECAST columns)."""
    return series.groupby(series.index.normalize()).transform("mean")


def build_features(df: pd.DataFrame, weekend_days: list[int]) -> pd.DataFrame:
    """All PV and load inputs, one row per slot, aligned with `df` (the M2 table)."""
    index = df.index
    day_of_year = index.day_of_year.to_numpy()
    features = pd.DataFrame(index=index)
    features["slot"] = df["slot"].to_numpy()
    features["day_of_week"] = index.day_of_week
    features["is_weekend"] = index.day_of_week.isin(weekend_days).astype(int)
    features["doy_sin"] = np.sin(2 * np.pi * day_of_year / 365.25)
    features["doy_cos"] = np.cos(2 * np.pi * day_of_year / 365.25)

    for column in ("ghi_forecast_wm2", "temp_forecast_c", "cloud_forecast_pct", "pv_forecast_kw"):
        features[column] = df[column]
    features["ghi_forecast_day_kwh_m2"] = same_day_mean(df["ghi_forecast_wm2"]) * 24 / 1000
    features["cloud_forecast_day_pct"] = same_day_mean(df["cloud_forecast_pct"])

    features["pv_lag1_kw"] = lag_days(df["pv_actual_kw"], 1)
    features["pv_lag1_day_kwh"] = daily_total_lag(df["pv_actual_kw"], 1, SLOT_H)
    features["load_lag1_kw"] = lag_days(df["base_load_kw"], 1)
    features["load_lag7_kw"] = lag_days(df["base_load_kw"], 7)
    features["load_lag1_day_kwh"] = daily_total_lag(df["base_load_kw"], 1, SLOT_H)
    return features
