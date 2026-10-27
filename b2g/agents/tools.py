"""What the orchestrator's actions do. The LLM sees compact summaries, never 96-number lists.

GET_FORECAST uses only the day-ahead forecast (`DayData` built by `sim.day.forecast_day`), so the
agents cannot see the actual day they are planning.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np

from b2g.agents.apply import apply_constraints
from b2g.agents.schemas import DayConstraints
from b2g.models import DT_H, SLOTS, site
from b2g.sim.day import Assets, DayData, State, calendar
from b2g.solver.milp import Plan, solve_day


def slot_time(slot: int) -> str:
    """15-min slot index -> 'HH:MM' (96 -> '24:00')."""
    return f"{slot * 15 // 60:02d}:{slot * 15 % 60:02d}"


def slots_to_ranges(mask) -> str:
    """bool[96] -> '00:00-08:00, 18:00-24:00' ('none' if empty)."""
    mask = np.asarray(mask, dtype=bool)
    ranges, start = [], None
    for t in range(SLOTS + 1):
        on = t < SLOTS and mask[t]
        if on and start is None:
            start = t
        elif not on and start is not None:
            ranges.append(f"{slot_time(start)}-{slot_time(t)}")
            start = None
    return ", ".join(ranges) or "none"


def charge_source(p_charge, grid_import) -> str:
    """'solar', 'grid', 'solar and grid' or 'none': battery charging in a slot counts as grid up to that slot's import."""
    charged = float(np.sum(p_charge))
    if charged < 1e-6:
        return "none"
    grid_share = float(np.minimum(p_charge, grid_import).sum()) / charged
    return "solar" if grid_share < 0.05 else "grid" if grid_share > 0.95 else "solar and grid"


def forecast_summary(forecast: DayData) -> dict[str, Any]:
    """Tomorrow at a glance, from the day-ahead forecast only."""
    pv, t_out, price = forecast.pv_kw, forecast.t_out_c, forecast.price
    sunny = pv >= 0.5 * pv.max() if pv.max() > 0 else np.zeros(SLOTS, dtype=bool)
    periods, start = [], 0
    for t in range(1, SLOTS + 1):
        if t == SLOTS or price[t] != price[start]:
            periods.append(f"{slot_time(start)}-{slot_time(t)}: {price[start]:g}")
            start = t
    return {
        "date": forecast.day.isoformat(),
        "weekday": forecast.day.strftime("%A"),
        "pv_forecast_kwh": round(float(pv.sum() * DT_H), 1),
        "pv_strong_hours": slots_to_ranges(sunny),
        "outdoor_temp_c": {"min": round(float(t_out.min()), 1), "max": round(float(t_out.max()), 1),
                           "hottest_at": slot_time(int(t_out.argmax()))},
        "base_load_forecast_kwh": round(float(forecast.base_kw.sum() * DT_H), 1),
        "price_per_kwh_by_period": periods,
    }


def calendar_info(assets: Assets, day: date) -> dict[str, Any]:
    """The usual routine and the configured defaults the agents start from."""
    ev_day, occupied = calendar(assets, day)
    car, bat, room = assets.ev, assets.battery, assets.thermal
    return {
        "date": day.isoformat(),
        "weekday": day.strftime("%A"),
        "ev": {"trip_today": ev_day.departure_slot is not None,
               "departure_time": slot_time(ev_day.departure_slot) if ev_day.departure_slot is not None else None,
               "arrival_time": slot_time(ev_day.arrival_slot) if ev_day.arrival_slot is not None else None,
               "target_soc": car.target_soc, "battery_kwh": car.capacity_kwh, "charger_max_kw": car.p_max_kw},
        "home_battery": {"capacity_kwh": bat.capacity_kwh, "reserve_soc": bat.soc_min, "grid_charging_allowed": True},
        "comfort": {"comfort_min_c": room.comfort_min_c, "comfort_max_c": room.comfort_max_c,
                    "someone_home": slots_to_ranges(occupied), "ac_max_kw": room.p_cool_max_kw},
    }


def run_solver(assets: Assets, forecast: DayData, state: State, constraints: DayConstraints) -> tuple[Plan, Assets, dict[str, Any]]:
    """Apply the constraints, solve on the forecast, and summarise the plan for the orchestrator."""
    day_assets, notes = apply_constraints(assets, forecast.day, constraints)
    ev_day, occupied = calendar(day_assets, forecast.day)
    plan = solve_day(day_assets, forecast, ev_day, occupied, state)
    a = plan.actions
    home_temps = plan.temps[1:][occupied]
    summary = {
        "solver_status": plan.status,
        "estimated_electricity_cost": round(site.daily_cost(forecast.price, plan.grid_import, plan.grid_export,
                                                            assets.grid.export_price), 2),
        "ev": {"departure": slot_time(ev_day.departure_slot) if ev_day.departure_slot is not None else "no trip",
               "target_kwh": round(ev_day.target_kwh, 1),
               "kwh_at_departure": round(float(plan.e_ev[ev_day.departure_slot]), 1) if ev_day.departure_slot is not None else None,
               "target_met": plan.ev_short_kwh < 0.01, "charging": slots_to_ranges(a.p_ev > 0.05)},
        "room": {"comfort_band_c": [day_assets.thermal.comfort_min_c, day_assets.thermal.comfort_max_c],
                 "someone_home": slots_to_ranges(occupied), "ac_on": slots_to_ranges(a.p_cool > 0.05),
                 "max_temp_when_home_c": round(float(home_temps.max()), 1) if home_temps.size else None,
                 "planned_discomfort_degC_h": round(plan.comfort_slack_dh, 2)},
        "home_battery": {"reserve_kwh": round(day_assets.battery.e_min_kwh, 1),
                         "lowest_planned_kwh": round(float(plan.e_bat.min()), 1),
                         "charging": slots_to_ranges(a.p_charge > 0.05), "charged_from": charge_source(a.p_charge, plan.grid_import),
                         "discharging": slots_to_ranges(a.p_discharge > 0.05)},
        "grid": {"peak_import_kw": round(float(plan.grid_import.max()), 2), "limit_kw": assets.grid.import_limit_kw},
        "notes": notes,
    }
    return plan, day_assets, summary
