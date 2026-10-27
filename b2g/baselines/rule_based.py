"""S1: rule-based control, no forecast (lower bound). Decides slot by slot from what it measures now.

- AC: thermostat, full power while someone is home and the room is above comfort_max.
- EV: full power whenever at home until the target charge is reached; with `respect_limit` the
  charger slows down so the house stays under the grid import limit (basic load management).
- Battery: stores surplus PV and covers shortfalls (self-consumption), within its limits.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np

from b2g.models import DT_H, SLOTS, thermal
from b2g.sim.day import Actions, Assets, DayData, State, calendar


def rule_based_actions(assets: Assets, actual: DayData, state: State, respect_limit: bool = True) -> Actions:
    """Run the rules through the actual day (they react to measurements, so they see actuals as they happen)."""
    bat, car, room, grid = assets.battery, assets.ev, assets.thermal, assets.grid
    ev_day, occupied = calendar(assets, actual.day)
    gains = thermal.heat_gains_kw(room, actual.ghi_wm2, occupied)
    pc, pd, p_ev, p_cool = (np.zeros(SLOTS) for _ in range(4))
    e_bat, e_ev, temp = state.e_bat_kwh, state.e_ev_kwh, state.t_room_c

    for t in range(SLOTS):
        p_cool[t] = room.p_cool_max_kw if occupied[t] and temp > room.comfort_max_c else 0.0

        if ev_day.at_home[t] and e_ev < ev_day.target_kwh:
            p_ev[t] = min(car.p_max_kw, (ev_day.target_kwh - e_ev) / (car.eta_charge * DT_H))
            if respect_limit:
                others = actual.base_kw[t] + p_cool[t] - actual.pv_kw[t]
                p_ev[t] = max(0.0, min(p_ev[t], grid.import_limit_kw - others))

        net = actual.base_kw[t] + p_cool[t] + p_ev[t] - actual.pv_kw[t]
        if net < 0:
            room_kw = max(bat.e_max_kwh - e_bat, 0.0) / (bat.eta_charge * DT_H)
            pc[t] = min(-net, bat.p_charge_max_kw, room_kw)
        elif net > 0:
            available_kw = max(e_bat - bat.e_min_kwh, 0.0) * bat.eta_discharge / DT_H
            pd[t] = min(net, bat.p_discharge_max_kw, available_kw)

        e_bat += bat.eta_charge * pc[t] * DT_H - pd[t] * DT_H / bat.eta_discharge
        e_ev += car.eta_charge * p_ev[t] * DT_H
        if ev_day.arrival_slot is not None and t + 1 == ev_day.arrival_slot:
            e_ev = max(e_ev - ev_day.trip_kwh, 0.0)
        heat = (actual.t_out_c[t] - temp) / room.r_c_per_kw + gains[t] - room.cop * p_cool[t]
        temp += DT_H / room.c_kwh_per_c * heat
    return Actions(pc, pd, p_ev, p_cool)


def make_system(assets: Assets, actual_for, respect_limit: bool = True):
    """S1 as a `System` for sim.simulate.run_days."""
    def system(day: date, state: State) -> tuple[Actions, dict[str, Any]]:
        return rule_based_actions(assets, actual_for(day), state, respect_limit), {}
    return system
