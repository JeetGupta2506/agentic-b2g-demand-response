"""S2 (forecast + MILP, no LLM) and S5 (oracle: MILP on actual data). Both plan the whole day ahead."""

from __future__ import annotations

from datetime import date
from typing import Any, Callable

from b2g.sim.day import Actions, Assets, DayData, State, calendar
from b2g.solver.milp import solve_day


def make_planner(assets: Assets, data_for: Callable[[date], DayData]):
    """A `System` that solves the MILP on `data_for(day)` (forecast -> S2, actual -> S5)."""
    def system(day: date, state: State) -> tuple[Actions, dict[str, Any]]:
        ev_day, occupied = calendar(assets, day)
        plan = solve_day(assets, data_for(day), ev_day, occupied, state)
        return plan.actions, {"planned_objective": plan.objective, "solve_s": plan.solve_s,
                              "planned_ev_short_kwh": plan.ev_short_kwh}
    return system
