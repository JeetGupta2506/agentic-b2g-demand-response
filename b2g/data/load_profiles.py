"""Synthetic non-flexible household base load (kW per 15-min slot)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def base_load_kw(slots: pd.DatetimeIndex, cfg: dict[str, Any], seed: int) -> pd.Series:
    """
    Base load (kW, average over each 15-min slot) for the given slot start times.

    Each day: daily energy (kWh, weekday or weekend) x normalised hourly shape gives the hourly
    energy, i.e. the mean kW in that hour; every slot then gets multiplicative noise
    N(1, noise_std), clipped at 0.05. The noise uses a generator seeded by (seed, date), so a day's
    profile is identical whatever date range is built.
    """
    shapes = {
        False: np.asarray(cfg["hourly_shape_weekday"], dtype=float),
        True: np.asarray(cfg["hourly_shape_weekend"], dtype=float),
    }
    if any(len(s) != 24 for s in shapes.values()):
        raise ValueError("hourly shapes need 24 values")
    daily_kwh = {False: cfg["daily_kwh_weekday"], True: cfg["daily_kwh_weekend"]}
    weekend_days = set(cfg["weekend_days"])

    values = np.empty(len(slots))
    for day, positions in pd.Series(np.arange(len(slots)), index=slots).groupby(slots.normalize()):
        is_weekend = day.weekday() in weekend_days
        hourly_kw = daily_kwh[is_weekend] * shapes[is_weekend] / shapes[is_weekend].sum()
        day_slots = slots[positions.to_numpy()]
        rng = np.random.default_rng([seed, day.toordinal()])
        noise = (1 + cfg["noise_std"] * rng.standard_normal(96)).clip(min=0.05)
        slot_of_day = day_slots.hour * 4 + day_slots.minute // 15
        values[positions.to_numpy()] = hourly_kw[day_slots.hour] * noise[slot_of_day]
    return pd.Series(values, index=slots, name="base_load_kw")
