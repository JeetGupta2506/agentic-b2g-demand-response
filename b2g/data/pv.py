"""Rooftop PV output from irradiance."""

from __future__ import annotations

import pandas as pd


def pv_power_kw(ghi_wm2: pd.Series, kwp: float, derate: float) -> pd.Series:
    """
    PV power (kW) per slot: P = kWp x GHI/1000 x derate (plan section 4).

    ghi_wm2: global horizontal irradiance (W/m2), mean over the slot. 1000 W/m2 is the
    standard test condition at which a kWp array delivers kWp before losses. Never negative.
    """
    return (kwp * ghi_wm2 / 1000.0 * derate).clip(lower=0).rename("pv_kw")
