"""Settle a day's actions against ACTUAL data and roll systems over several days (plan section 5).

EV and AC run as planned (EV clipped to what is physically possible: at home, charger limit, battery
not overfull); the battery runs as planned but clipped to feasibility; the grid absorbs the rest.
Violations: grid import above the limit, or the EV short of its target at departure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Callable

import numpy as np

from b2g.models import DT_H, TOL, battery, ev, site, thermal
from b2g.sim.day import Actions, Assets, DayData, State, calendar


@dataclass(frozen=True)
class DayResult:
    """What actually happened on one day under one system, with its metrics."""

    day: date
    system: str
    applied: Actions          # after clipping
    grid_import: np.ndarray
    grid_export: np.ndarray
    e_bat: np.ndarray
    e_ev: np.ndarray
    temps: np.ndarray
    end_state: State
    metrics: dict[str, Any]
    violations: list[str] = field(default_factory=list)


def settle(assets: Assets, actions: Actions, actual: DayData, state: State, system: str = "") -> DayResult:
    """Apply `actions` on the actual day starting from `state`; compute flows, comfort and metrics."""
    ev_day, occupied = calendar(assets, actual.day)
    p_charge, p_discharge, e_bat = battery.clip_to_feasible(assets.battery, actions.p_charge, actions.p_discharge, state.e_bat_kwh)
    p_ev, e_ev = ev.clip_to_feasible(assets.ev, ev_day, actions.p_ev, state.e_ev_kwh)
    p_cool = np.clip(np.asarray(actions.p_cool, dtype=float), 0, assets.thermal.p_cool_max_kw)

    gains = thermal.heat_gains_kw(assets.thermal, actual.ghi_wm2, occupied)
    temps = thermal.simulate(assets.thermal, actual.t_out_c, gains, p_cool, state.t_room_c)
    net = site.net_load_kw(actual.base_kw, actual.pv_kw, p_ev, p_cool, p_charge, p_discharge)
    g_imp, g_exp = site.grid_flows(net)

    violations = site.check_import_limit(assets.grid, g_imp)
    ev_short = ev.unmet_energy_kwh(assets.ev, ev_day, p_ev, state.e_ev_kwh)
    if ev_short > TOL:
        violations.append(f"EV {ev_short:.2f} kWh short at departure")

    w = assets.weights
    electricity = site.daily_cost(actual.price, g_imp, g_exp, assets.grid.export_price)
    throughput = float((p_charge + p_discharge).sum() * DT_H)
    comfort_dh = thermal.comfort_violation_degree_hours(assets.thermal, temps, occupied)
    metrics = {
        "electricity_cost": electricity,
        "battery_wear_cost": w["w_battery_wear"] * throughput,
        "comfort_dh": comfort_dh,
        "comfort_penalty": w["w_comfort"] * comfort_dh,
        "ev_unmet_kwh": ev_short,
        "ev_penalty": w["w_ev_unmet"] * ev_short,
        "peak_import_kw": site.peak_import_kw(g_imp),
        "import_kwh": float(g_imp.sum() * DT_H),
        "export_kwh": float(g_exp.sum() * DT_H),
        "pv_kwh": float(actual.pv_kw.sum() * DT_H),
        "self_consumption_pct": site.self_consumption_pct(actual.pv_kw, g_exp),
        "ac_kwh": float(p_cool.sum() * DT_H),
        "ev_kwh": float(p_ev.sum() * DT_H),
        "violation": bool(violations),
    }
    metrics["total_cost"] = (metrics["electricity_cost"] + metrics["battery_wear_cost"]
                             + metrics["comfort_penalty"] + metrics["ev_penalty"])
    end = State(float(e_bat[-1]), float(e_ev[-1]), float(temps[-1]))
    return DayResult(actual.day, system, Actions(p_charge, p_discharge, p_ev, p_cool), g_imp, g_exp, e_bat, e_ev,
                     temps, end, metrics, violations)


# A system decides the day's actions given the start state; it returns actions and extra info.
System = Callable[[date, State], tuple[Actions, dict[str, Any]]]


def run_days(assets: Assets, name: str, system: System, actual_for: Callable[[date], DayData],
             start: date, n_days: int, state: State | None = None) -> list[DayResult]:
    """Run `system` day after day; each day starts from the previous day's ACTUAL end state."""
    state = state or State.initial(assets)
    results = []
    for k in range(n_days):
        day = start + timedelta(days=k)
        actions, info = system(day, state)
        result = settle(assets, actions, actual_for(day), state, name)
        result.metrics.update(info)
        results.append(result)
        state = result.end_state
    return results
