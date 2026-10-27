"""Home battery: SoC[t+1] = SoC[t] + eta_c * Pc[t] * dt - Pd[t] * dt / eta_d (plan section 4).

Energies in kWh (the array has 97 entries: start of every slot plus end of day), powers in kW.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from b2g.models import DT_H, SLOTS, TOL, as_profile


@dataclass(frozen=True)
class BatteryParams:
    capacity_kwh: float
    p_charge_max_kw: float
    p_discharge_max_kw: float
    eta_charge: float
    eta_discharge: float
    soc_min: float      # fraction of capacity
    soc_max: float
    soc_initial: float

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "BatteryParams":
        return cls(**cfg["battery"])

    @property
    def e_min_kwh(self) -> float:
        return self.soc_min * self.capacity_kwh

    @property
    def e_max_kwh(self) -> float:
        return self.soc_max * self.capacity_kwh

    @property
    def e_initial_kwh(self) -> float:
        return self.soc_initial * self.capacity_kwh


def simulate(params: BatteryParams, p_charge, p_discharge, e0_kwh: float) -> np.ndarray:
    """Stored energy (kWh) at the start of each slot and at the end of the day (97 values). No clipping."""
    pc, pd = as_profile(p_charge, "p_charge"), as_profile(p_discharge, "p_discharge")
    steps = params.eta_charge * pc * DT_H - pd * DT_H / params.eta_discharge
    return e0_kwh + np.concatenate([[0.0], np.cumsum(steps)])


def check(params: BatteryParams, p_charge, p_discharge, e0_kwh: float) -> list[str]:
    """Every physical limit the plan breaks (empty list = feasible)."""
    pc, pd = as_profile(p_charge, "p_charge"), as_profile(p_discharge, "p_discharge")
    energy = simulate(params, pc, pd, e0_kwh)
    problems = []
    for t in range(SLOTS):
        if pc[t] < -TOL or pd[t] < -TOL:
            problems.append(f"battery slot {t}: negative power (charge {pc[t]:.3f}, discharge {pd[t]:.3f} kW)")
        if pc[t] > params.p_charge_max_kw + TOL:
            problems.append(f"battery slot {t}: charge {pc[t]:.3f} kW > max {params.p_charge_max_kw} kW")
        if pd[t] > params.p_discharge_max_kw + TOL:
            problems.append(f"battery slot {t}: discharge {pd[t]:.3f} kW > max {params.p_discharge_max_kw} kW")
        if pc[t] > TOL and pd[t] > TOL:
            problems.append(f"battery slot {t}: charging and discharging at the same time")
    for t, e in enumerate(energy):
        if e < params.e_min_kwh - TOL:
            problems.append(f"battery t={t}: stored {e:.3f} kWh < min {params.e_min_kwh:.3f} kWh")
        if e > params.e_max_kwh + TOL:
            problems.append(f"battery t={t}: stored {e:.3f} kWh > max {params.e_max_kwh:.3f} kWh")
    return problems


def clip_to_feasible(params: BatteryParams, p_charge, p_discharge, e0_kwh: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    The closest physically possible operation of a plan, slot by slot (used when settling a plan on
    actual data): simultaneous charge/discharge is netted, powers are capped at their limits and at
    what the remaining capacity / stored energy allows. Returns (p_charge, p_discharge, energy).
    """
    pc_in, pd_in = as_profile(p_charge, "p_charge"), as_profile(p_discharge, "p_discharge")
    pc, pd = np.zeros(SLOTS), np.zeros(SLOTS)
    energy = np.empty(SLOTS + 1)
    energy[0] = e = e0_kwh
    for t in range(SLOTS):
        net = max(pc_in[t], 0.0) - max(pd_in[t], 0.0)
        if net > 0:
            headroom_kw = max(params.e_max_kwh - e, 0.0) / (params.eta_charge * DT_H)
            pc[t] = min(net, params.p_charge_max_kw, headroom_kw)
        elif net < 0:
            available_kw = max(e - params.e_min_kwh, 0.0) * params.eta_discharge / DT_H
            pd[t] = min(-net, params.p_discharge_max_kw, available_kw)
        e = e + params.eta_charge * pc[t] * DT_H - pd[t] * DT_H / params.eta_discharge
        energy[t + 1] = e
    return pc, pd, energy
