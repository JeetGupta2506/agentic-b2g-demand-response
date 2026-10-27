"""Electricity buy price per 15-min slot from one of three pluggable sources (plan section 4)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from b2g import REPO_ROOT


def _hhmm_to_minutes(text: str) -> int:
    """'09:30' -> 570; '24:00' allowed as end of day."""
    hours, minutes = text.split(":")
    return int(hours) * 60 + int(minutes)


def tou_prices(slots: pd.DatetimeIndex, periods: list[dict[str, Any]]) -> pd.Series:
    """
    Time-of-use price per slot. `periods` must cover 00:00-24:00 without gaps or overlaps;
    each is {start: "HH:MM", end: "HH:MM", price: float}. Slot boundaries must align with periods.
    """
    edges = sorted((_hhmm_to_minutes(p["start"]), _hhmm_to_minutes(p["end"]), float(p["price"])) for p in periods)
    if edges[0][0] != 0 or edges[-1][1] != 24 * 60 or any(a[1] != b[0] for a, b in zip(edges, edges[1:])):
        raise ValueError("tariff periods must cover 00:00-24:00 without gaps or overlaps")
    if any(s % 15 or e % 15 for s, e, _ in edges):
        raise ValueError("tariff periods must start and end on 15-min boundaries")
    by_slot = np.empty(96)
    for start, end, price in edges:
        by_slot[start // 15:end // 15] = price
    slot_of_day = slots.hour * 4 + slots.minute // 15
    return pd.Series(by_slot[slot_of_day], index=slots, name="price")


def sample_prices(slots: pd.DatetimeIndex, path: str | Path) -> pd.Series:
    """The original repo's 96 sample prices (EUR/MWh), converted to EUR/kWh and repeated every day."""
    data = json.loads((REPO_ROOT / path).read_text(encoding="utf-8"))
    by_slot = np.asarray(data["prices"], dtype=float) / 1000.0
    if len(by_slot) != 96:
        raise ValueError(f"expected 96 sample prices, got {len(by_slot)}")
    return pd.Series(by_slot[slots.hour * 4 + slots.minute // 15], index=slots, name="price")


def csv_prices(slots: pd.DatetimeIndex, cfg: dict[str, Any]) -> pd.Series:
    """
    Prices from a CSV with one row per 15-min block (e.g. IEX day-ahead market), local start time.
    Values are divided by cfg["divisor"] (1000 turns per-MWh into per-kWh). Every slot must be present.
    """
    if not cfg.get("path"):
        raise ValueError("tariff.csv.path is not set in the config")
    table = pd.read_csv(REPO_ROOT / cfg["path"], parse_dates=[cfg["time_column"]])
    series = table.set_index(cfg["time_column"])[cfg["price_column"]].astype(float) / cfg["divisor"]
    aligned = series.reindex(slots)
    if aligned.isna().any():
        missing = aligned.index[aligned.isna()]
        raise ValueError(f"price CSV lacks {len(missing)} slots, first {missing[0]}")
    return aligned.rename("price")


def price_series(slots: pd.DatetimeIndex, tariff: dict[str, Any]) -> tuple[pd.Series, str]:
    """Buy price per slot from the configured source; returns (prices, unit)."""
    source = tariff["source"]
    if source == "tou":
        return tou_prices(slots, tariff["tou"]["periods"]), tariff["tou"]["unit"]
    if source == "sample":
        return sample_prices(slots, tariff["sample"]["path"]), tariff["sample"]["unit"]
    if source == "csv":
        return csv_prices(slots, tariff["csv"]), tariff["csv"]["unit"]
    raise ValueError(f"unknown tariff source '{source}' (tou | sample | csv)")
