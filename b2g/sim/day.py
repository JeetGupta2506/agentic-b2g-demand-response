"""What a system knows about one day: the 96-slot series, the device parameters and the start state.

The same `DayData` type holds either the day-ahead forecast (what a planner sees) or the actual day
(what the simulator settles against), so planners and the simulator cannot mix them up by accident.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from b2g.models import SLOTS, as_profile, battery, ev, site, thermal


@dataclass(frozen=True)
class Assets:
    """All device parameters plus the solver weights, from the config."""

    battery: battery.BatteryParams
    ev: ev.EVParams
    thermal: thermal.ThermalParams
    grid: site.GridParams
    weekend_days: list[int]
    weights: dict[str, Any]

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "Assets":
        return cls(battery.BatteryParams.from_config(cfg), ev.EVParams.from_config(cfg),
                   thermal.ThermalParams.from_config(cfg), site.GridParams.from_config(cfg),
                   list(cfg["base_load"]["weekend_days"]), dict(cfg["solver"]))


@dataclass(frozen=True)
class DayData:
    """96-slot series for one day: price per kWh, PV and base load in kW, outdoor degC, GHI in W/m2."""

    day: date
    price: np.ndarray
    pv_kw: np.ndarray
    base_kw: np.ndarray
    t_out_c: np.ndarray
    ghi_wm2: np.ndarray
    source: str  # "actual" or the forecaster used, e.g. "forecast:pv=lgbm,load=lgbm"

    def __post_init__(self) -> None:
        for name in ("price", "pv_kw", "base_kw", "t_out_c", "ghi_wm2"):
            object.__setattr__(self, name, as_profile(getattr(self, name), name))


@dataclass(frozen=True)
class Actions:
    """Controllable powers per slot (kW): what a system tells the devices to do."""

    p_charge: np.ndarray
    p_discharge: np.ndarray
    p_ev: np.ndarray
    p_cool: np.ndarray


@dataclass(frozen=True)
class State:
    """Device states at 00:00: battery and EV energy in kWh, room temperature in degC."""

    e_bat_kwh: float
    e_ev_kwh: float
    t_room_c: float

    @classmethod
    def initial(cls, assets: Assets, e_ev_kwh: float | None = None) -> "State":
        """Configured start: battery at soc_initial, room at t_initial, EV as just back from a trip
        (target - trip, i.e. 40 % with the defaults) unless given."""
        default_ev = max(assets.ev.target_kwh - assets.ev.trip_kwh, 0.0)
        return cls(assets.battery.e_initial_kwh, default_ev if e_ev_kwh is None else e_ev_kwh, assets.thermal.t_initial_c)


def calendar(assets: Assets, day: date) -> tuple[ev.EVDay, np.ndarray]:
    """The EV's day and the occupancy mask (both known in advance)."""
    return ev.ev_day(assets.ev, day, assets.weekend_days), thermal.occupancy(assets.thermal, day, assets.weekend_days)


def _one_day(table: pd.DataFrame, day: date) -> pd.DataFrame:
    rows = table[table.index.normalize() == pd.Timestamp(day)]
    if len(rows) != SLOTS:
        raise ValueError(f"{day}: expected {SLOTS} slots, found {len(rows)}")
    return rows


def actual_day(df: pd.DataFrame, day: date) -> DayData:
    """What really happened (M2 table)."""
    rows = _one_day(df, day)
    return DayData(day, rows["price"], rows["pv_actual_kw"], rows["base_load_kw"], rows["temp_actual_c"],
                   rows["ghi_actual_wm2"], "actual")


def forecast_day(df: pd.DataFrame, forecasts: pd.DataFrame, day: date, pv_model: str, load_model: str) -> DayData:
    """What a day-ahead planner sees: M3 PV/load forecasts, weather forecast, and the (known) tariff."""
    rows, fc = _one_day(df, day), _one_day(forecasts, day)
    return DayData(day, rows["price"], fc[f"pv_{pv_model}"], fc[f"load_{load_model}"], rows["temp_forecast_c"],
                   rows["ghi_forecast_wm2"], f"forecast:pv={pv_model},load={load_model}")
