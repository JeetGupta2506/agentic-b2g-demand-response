"""Turn the agents' DayConstraints into solver/simulator inputs for one day.

The result is an `Assets` copy whose EV, battery and thermal parameters describe that day, so the
planner (MILP) and the settlement on actual data (`sim.simulate.settle`, which derives the calendar
from the assets) use exactly the same rules. Merging may need small fixes (e.g. a new comfort max
below the default min); each fix is reported as a note.
"""

from __future__ import annotations

import dataclasses
from datetime import date

from b2g.agents.schemas import DayConstraints, minutes
from b2g.sim.day import Assets


def apply_constraints(assets: Assets, day: date, constraints: DayConstraints) -> tuple[Assets, list[str]]:
    """Assets for `day` with the constraints applied, plus notes about any automatic fixes."""
    notes: list[str] = []
    ev_c, bat_c, room_c = constraints.ev, constraints.battery, constraints.precool
    weekend = day.weekday() in assets.weekend_days

    # EV: new times make it a trip day even on a weekend
    car = assets.ev
    if ev_c.departure_time or ev_c.arrival_time:
        departure = ev_c.departure_time or car.departure
        arrival = ev_c.arrival_time or car.arrival
        if minutes(departure) >= minutes(arrival):
            notes.append(f"EV: departure {departure} is not before arrival {arrival}; car assumed away until 24:00")
            arrival = "24:00"
        car = dataclasses.replace(car, departure=departure, arrival=arrival, weekend_at_home=False)
    if ev_c.target_soc is not None:
        car = dataclasses.replace(car, target_soc=ev_c.target_soc)
    if ev_c.max_power_kw is not None:
        car = dataclasses.replace(car, p_max_kw=min(ev_c.max_power_kw, car.p_max_kw))
    if ev_c.skip_charging:
        car = dataclasses.replace(car, p_max_kw=0.0, target_soc=0.0)

    # Battery: a reserve can only raise the minimum
    bat = assets.battery
    if bat_c.reserve_soc is not None:
        if bat_c.reserve_soc < bat.soc_min:
            notes.append(f"battery: reserve {bat_c.reserve_soc:.0%} below the technical minimum {bat.soc_min:.0%}; kept the minimum")
        bat = dataclasses.replace(bat, soc_min=max(bat.soc_min, bat_c.reserve_soc))
    weights = dict(assets.weights)
    if bat_c.allow_grid_charging is not None:
        weights["battery_grid_charging"] = bat_c.allow_grid_charging

    # Room: comfort band and who is home (written into both away fields: these rules are for this day only)
    room = assets.thermal
    lo = room_c.comfort_min_c if room_c.comfort_min_c is not None else room.comfort_min_c
    hi = room_c.comfort_max_c if room_c.comfort_max_c is not None else room.comfort_max_c
    if lo >= hi:
        notes.append(f"comfort: min {lo} degC not below max {hi} degC; min set to {hi - 2} degC")
        lo = hi - 2
    room = dataclasses.replace(room, comfort_min_c=lo, comfort_max_c=hi)
    default_away = room.weekend_away if weekend else room.weekday_away
    if room_c.home_all_day:
        away = None
    elif room_c.away_from or room_c.away_until:
        start = room_c.away_from or (default_away or {}).get("start", "08:00")
        end = room_c.away_until or (default_away or {}).get("end", "18:00")
        if minutes(start) >= minutes(end):
            notes.append(f"occupancy: away {start}-{end} is empty; treated as home all day")
            away = None
        else:
            away = {"start": start, "end": end}
    else:
        away = default_away
    room = dataclasses.replace(room, weekday_away=away, weekend_away=away)

    return dataclasses.replace(assets, ev=car, battery=bat, thermal=room, weights=weights), notes
