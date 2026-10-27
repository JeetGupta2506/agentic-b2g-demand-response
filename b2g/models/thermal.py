"""Room temperature, linear 1R1C model with an AC (plan section 4):

    T[t+1] = T[t] + dt/C * ( (T_out[t] - T[t])/R + Q_gain[t] - COP * P_cool[t] )

R in degC/kW, C in kWh/degC, powers in kW (P_cool electric), temperatures in degC (97 values: start of
every slot plus end of day). Q_gain = solar gain (from GHI) + internal gain while occupied. The comfort
band applies only to occupied slots and is checked on the temperature at the END of each slot (T[t+1]),
the first temperature the slot's cooling can influence.

Same structure as the original repo's unfinished heat-pump model (tools.calculate_heating_requirement:
heat loss = dT/R, temperature change = net heat x dt / C), rewritten for cooling with a COP.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np

from b2g.models import DT_H, SLOTS, TOL, as_profile, hhmm_to_slot


@dataclass(frozen=True)
class ThermalParams:
    r_c_per_kw: float
    c_kwh_per_c: float
    cop: float
    p_cool_max_kw: float
    solar_gain_kw_per_kw_m2: float
    internal_gain_kw: float
    comfort_min_c: float
    comfort_max_c: float
    t_min_c: float
    t_initial_c: float
    weekday_away: dict[str, str] | None
    weekend_away: dict[str, str] | None

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "ThermalParams":
        params = cls(**cfg["thermal"])
        if DT_H / (params.r_c_per_kw * params.c_kwh_per_c) >= 1:
            raise ValueError("thermal time constant R*C must exceed the 15-min step (explicit model unstable)")
        return params


def occupancy(params: ThermalParams, day: date, weekend_days: list[int]) -> np.ndarray:
    """bool[96]: someone is home (comfort band enforced)."""
    away = params.weekend_away if day.weekday() in weekend_days else params.weekday_away
    occupied = np.ones(SLOTS, dtype=bool)
    if away:
        occupied[hhmm_to_slot(away["start"]):hhmm_to_slot(away["end"])] = False
    return occupied


def heat_gains_kw(params: ThermalParams, ghi_wm2, occupied) -> np.ndarray:
    """Heat entering the room (kW): solar through windows/roof plus people and devices when home."""
    ghi = as_profile(ghi_wm2, "ghi_wm2")
    return params.solar_gain_kw_per_kw_m2 * np.clip(ghi, 0, None) / 1000 + params.internal_gain_kw * np.asarray(occupied, dtype=float)


def simulate(params: ThermalParams, t_out_c, gains_kw, p_cool_kw, t0_c: float) -> np.ndarray:
    """Room temperature (degC) at the start of each slot and at the end of the day."""
    t_out = as_profile(t_out_c, "t_out_c")
    gains = as_profile(gains_kw, "gains_kw")
    p_cool = as_profile(p_cool_kw, "p_cool_kw")
    temps = np.empty(SLOTS + 1)
    temps[0] = t = t0_c
    for k in range(SLOTS):
        heat_kw = (t_out[k] - t) / params.r_c_per_kw + gains[k] - params.cop * p_cool[k]
        t = t + DT_H / params.c_kwh_per_c * heat_kw
        temps[k + 1] = t
    return temps


def steady_state_c(params: ThermalParams, t_out_c: float, gain_kw: float, p_cool_kw: float) -> float:
    """Temperature the room settles at under constant conditions: T_out + R * (gain - COP * P_cool)."""
    return t_out_c + params.r_c_per_kw * (gain_kw - params.cop * p_cool_kw)


def comfort_violation_degree_hours(params: ThermalParams, temps_c, occupied) -> float:
    """Sum over occupied slots of how far T[t+1] is outside the comfort band, x 0.25 h (degC*h)."""
    end_temps = np.asarray(temps_c, dtype=float)[1:]
    occupied = np.asarray(occupied, dtype=bool)
    outside = np.clip(end_temps - params.comfort_max_c, 0, None) + np.clip(params.comfort_min_c - end_temps, 0, None)
    return float((outside * occupied).sum() * DT_H)


def check(params: ThermalParams, temps_c, occupied, p_cool_kw) -> list[str]:
    """AC limits and the hard minimum temperature. Comfort is reported separately (degree-hours)."""
    p = as_profile(p_cool_kw, "p_cool_kw")
    temps = np.asarray(temps_c, dtype=float)
    problems = [f"AC slot {k}: {p[k]:.3f} kW outside 0..{params.p_cool_max_kw} kW"
                for k in range(SLOTS) if p[k] < -TOL or p[k] > params.p_cool_max_kw + TOL]
    too_cold = np.nonzero(temps < params.t_min_c - TOL)[0]
    if len(too_cold):
        problems.append(f"room t={too_cold[0]}: {temps[too_cold[0]]:.2f} degC below the AC's minimum {params.t_min_c} degC")
    return problems
