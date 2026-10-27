"""Joint day-ahead MILP for battery, EV and AC under shared PV and a grid import limit (plan section 4).

Per slot t (dt = 0.25 h), all powers in kW, energies in kWh, temperatures in degC:
    battery  E[t+1] = E[t] + eta_c Pc[t] dt - Pd[t] dt / eta_d,  E_min <= E <= E_max,
             Pc <= Pc_max u[t],  Pd <= Pd_max (1 - u[t]),  u binary,  E[96] >= E[0]
    EV       V[t+1] = V[t] + eta P_ev[t] dt - trip [t+1 = arrival],  0 <= P_ev <= P_max at_home[t],
             0 <= V <= capacity,  V[departure] + short >= target
    room     T[t+1] = T[t] + dt/C ((T_out - T[t])/R + gain[t] - COP P_cool[t]),  0 <= P_cool <= P_max,
             (trip reduced by trip_gap >= 0 if the car left with less than the trip needs: it returns empty)
             occupied t:  comfort_min - lo[t] <= T[t+1] <= comfort_max + hi[t];  all t: T[t+1] >= t_min - cold[t]
    grid     G_imp - G_exp = base + P_ev + P_cool + Pc - Pd - PV,  0 <= G_imp <= limit,  G_exp >= 0,  peak >= G_imp
minimise  sum dt (price G_imp - export_price G_exp + w_wear (Pc + Pd)) + w_peak peak
          + w_comfort dt sum (lo + hi + cold) + w_ev (short + trip_gap)
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
import pulp

from b2g.models import DT_H, SLOTS, thermal
from b2g.models.ev import EVDay
from b2g.sim.day import Actions, Assets, DayData, State


@dataclass(frozen=True)
class Plan:
    """Solver output: the actions plus the trajectories it expects (on its own input data)."""

    actions: Actions
    grid_import: np.ndarray
    grid_export: np.ndarray
    e_bat: np.ndarray       # 97 values
    e_ev: np.ndarray        # 97 values
    temps: np.ndarray       # 97 values
    ev_short_kwh: float
    comfort_slack_dh: float
    objective: float
    status: str
    solve_s: float


def solve_day(assets: Assets, data: DayData, ev_day: EVDay, occupied: np.ndarray, state: State) -> Plan:
    """
    Cheapest schedule for one day given `data` (forecast or actual). Raises if the solver fails.

    battery_binary: true = always use the charge/discharge binary; false = LP relaxation; "auto" =
    solve the LP first (with losses and a wear cost, charging and discharging in the same slot only
    adds cost, so the LP optimum avoids it) and re-solve with the binary only if it ever happens.
    """
    mode = assets.weights.get("battery_binary", "auto")
    if mode == "auto":
        plan = _solve(assets, data, ev_day, occupied, state, binary=False)
        both = (plan.actions.p_charge > 1e-6) & (plan.actions.p_discharge > 1e-6)
        return _solve(assets, data, ev_day, occupied, state, binary=True) if both.any() else plan
    return _solve(assets, data, ev_day, occupied, state, binary=bool(mode))


def _solve(assets: Assets, data: DayData, ev_day: EVDay, occupied: np.ndarray, state: State, binary: bool) -> Plan:
    """Build and solve the model once."""
    w, bat, car, room, grid = assets.weights, assets.battery, assets.ev, assets.thermal, assets.grid
    gains = thermal.heat_gains_kw(room, data.ghi_wm2, occupied)
    T = range(SLOTS)
    prob = pulp.LpProblem("b2g_day", pulp.LpMinimize)
    var = lambda name, low=0.0, up=None: [pulp.LpVariable(f"{name}_{t}", lowBound=low, upBound=up) for t in T]

    pc, pd = var("pc", 0, bat.p_charge_max_kw), var("pd", 0, bat.p_discharge_max_kw)
    e_bat = [pulp.LpVariable(f"ebat_{t}", bat.e_min_kwh, bat.e_max_kwh) for t in range(SLOTS + 1)]
    p_ev = [pulp.LpVariable(f"pev_{t}", 0, car.p_max_kw if ev_day.at_home[t] else 0) for t in T]
    e_ev = [pulp.LpVariable(f"eev_{t}", 0, car.capacity_kwh) for t in range(SLOTS + 1)]
    p_cool = var("pcool", 0, room.p_cool_max_kw)
    temp = [pulp.LpVariable(f"temp_{t}") for t in range(SLOTS + 1)]
    hi, lo, cold = var("hi"), var("lo"), var("cold")
    g_imp, g_exp = var("gimp", 0, grid.import_limit_kw), var("gexp", 0)
    peak = pulp.LpVariable("peak", 0)
    ev_short = pulp.LpVariable("ev_short", 0)
    # Car left with less than the trip needs -> it comes back empty (as in models.ev.simulate), not "negative"
    trip_gap = pulp.LpVariable("trip_gap", 0, ev_day.trip_kwh)

    # Clamp the start state into the allowed range so rounding in the previous day can't make a day infeasible
    prob += e_bat[0] == min(max(state.e_bat_kwh, bat.e_min_kwh), bat.e_max_kwh)
    prob += e_ev[0] == min(max(state.e_ev_kwh, 0.0), car.capacity_kwh)
    prob += temp[0] == state.t_room_c
    prob += e_bat[SLOTS] >= e_bat[0]
    if binary:
        u = [pulp.LpVariable(f"u_{t}", cat="Binary") for t in T]
        for t in T:
            prob += pc[t] <= bat.p_charge_max_kw * u[t]
            prob += pd[t] <= bat.p_discharge_max_kw * (1 - u[t])
    for t in T:
        prob += e_bat[t + 1] == e_bat[t] + bat.eta_charge * DT_H * pc[t] - DT_H / bat.eta_discharge * pd[t]
        arriving = ev_day.arrival_slot is not None and t + 1 == ev_day.arrival_slot
        trip = ev_day.trip_kwh - trip_gap if arriving else 0.0
        prob += e_ev[t + 1] == e_ev[t] + car.eta_charge * DT_H * p_ev[t] - trip
        prob += temp[t + 1] == temp[t] + DT_H / room.c_kwh_per_c * (
            (float(data.t_out_c[t]) - temp[t]) / room.r_c_per_kw + float(gains[t]) - room.cop * p_cool[t])
        if occupied[t]:
            prob += temp[t + 1] <= room.comfort_max_c + hi[t]
            prob += temp[t + 1] >= room.comfort_min_c - lo[t]
        else:
            prob += hi[t] == 0
            prob += lo[t] == 0
        prob += temp[t + 1] >= room.t_min_c - cold[t]
        prob += g_imp[t] - g_exp[t] == float(data.base_kw[t]) + p_ev[t] + p_cool[t] + pc[t] - pd[t] - float(data.pv_kw[t])
        if not w.get("battery_grid_charging", True):   # person asked: charge the battery from surplus PV only
            prob += pc[t] <= max(float(data.pv_kw[t]) - float(data.base_kw[t]), 0.0)
        prob += peak >= g_imp[t]
    if ev_day.departure_slot is not None:
        prob += e_ev[ev_day.departure_slot] + ev_short >= ev_day.target_kwh
    else:
        prob += ev_short == 0

    prob += (pulp.lpSum(DT_H * (float(data.price[t]) * g_imp[t] - grid.export_price * g_exp[t]
                                + w["w_battery_wear"] * (pc[t] + pd[t])) for t in T)
             + w["w_peak"] * peak
             + w["w_comfort"] * DT_H * pulp.lpSum(hi[t] + lo[t] + cold[t] for t in T)
             + w["w_ev_unmet"] * (ev_short + trip_gap))

    start = time.perf_counter()
    prob.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=w.get("time_limit_s", 60), threads=w.get("threads", 1)))
    solve_s = time.perf_counter() - start
    status = pulp.LpStatus[prob.status]
    if status != "Optimal":
        raise RuntimeError(f"{data.day}: solver status {status}")

    val = lambda xs: np.array([x.value() or 0.0 for x in xs])
    actions = Actions(val(pc), val(pd), val(p_ev), val(p_cool))
    return Plan(actions, val(g_imp), val(g_exp), val(e_bat), val(e_ev), val(temp),
                float(ev_short.value() or 0.0), float(DT_H * (val(hi) + val(lo)).sum()),
                float(pulp.value(prob.objective)), f"{status} ({'MILP' if binary else 'LP'})", solve_s)
