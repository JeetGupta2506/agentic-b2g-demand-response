"""Electric car on the home charger.

Charging only while the car is at home, 0 <= P_ev <= P_max (continuous, a documented change from the
original's binary 7.4 kW), stored energy E[t+1] = E[t] + eta * P_ev[t] * dt, and on weekdays the battery
must hold the target energy at departure; the trip's energy is removed when the car comes back.
Energies in kWh (97 values: start of every slot plus end of day), powers in kW.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np

from b2g.models import DT_H, SLOTS, TOL, as_profile, hhmm_to_slot


@dataclass(frozen=True)
class EVParams:
    capacity_kwh: float
    p_max_kw: float
    eta_charge: float
    target_soc: float
    departure: str
    arrival: str
    trip_kwh: float
    weekend_at_home: bool

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "EVParams":
        return cls(**cfg["ev"])

    @property
    def target_kwh(self) -> float:
        return self.target_soc * self.capacity_kwh


@dataclass(frozen=True)
class EVDay:
    """The car's day: where it is per slot and its deadline (None on days without a trip)."""

    at_home: np.ndarray          # bool[96]
    departure_slot: int | None   # energy must be >= target_kwh at the start of this slot
    arrival_slot: int | None     # trip energy is removed at the start of this slot
    trip_kwh: float
    target_kwh: float


def ev_day(params: EVParams, day: date, weekend_days: list[int]) -> EVDay:
    """Weekday: away from departure to arrival with a deadline; weekend: at home all day, no deadline."""
    if day.weekday() in weekend_days and params.weekend_at_home:
        return EVDay(np.ones(SLOTS, dtype=bool), None, None, 0.0, params.target_kwh)
    departure, arrival = hhmm_to_slot(params.departure), hhmm_to_slot(params.arrival)
    at_home = np.ones(SLOTS, dtype=bool)
    at_home[departure:arrival] = False
    return EVDay(at_home, departure, arrival, params.trip_kwh, params.target_kwh)


def simulate(params: EVParams, day: EVDay, p_ev, e0_kwh: float) -> np.ndarray:
    """Stored energy (kWh) at the start of each slot and at the end of the day. No clipping."""
    p = as_profile(p_ev, "p_ev")
    energy = np.empty(SLOTS + 1)
    energy[0] = e = e0_kwh
    for t in range(SLOTS):
        e = e + params.eta_charge * p[t] * DT_H
        if day.arrival_slot is not None and t + 1 == day.arrival_slot:
            e = max(e - day.trip_kwh, 0.0)
        energy[t + 1] = e
    return energy


def unmet_energy_kwh(params: EVParams, day: EVDay, p_ev, e0_kwh: float) -> float:
    """Energy missing at departure (kWh); 0 on days without a deadline."""
    if day.departure_slot is None:
        return 0.0
    energy = simulate(params, day, p_ev, e0_kwh)
    return max(day.target_kwh - energy[day.departure_slot], 0.0)


def check(params: EVParams, day: EVDay, p_ev, e0_kwh: float) -> list[str]:
    """Physical limits the plan breaks plus a missed departure target (empty list = OK)."""
    p = as_profile(p_ev, "p_ev")
    energy = simulate(params, day, p, e0_kwh)
    problems = []
    for t in range(SLOTS):
        if p[t] < -TOL:
            problems.append(f"EV slot {t}: negative charging power {p[t]:.3f} kW")
        if p[t] > params.p_max_kw + TOL:
            problems.append(f"EV slot {t}: {p[t]:.3f} kW > charger max {params.p_max_kw} kW")
        if p[t] > TOL and not day.at_home[t]:
            problems.append(f"EV slot {t}: charging {p[t]:.3f} kW while the car is away")
    over = np.nonzero(energy > params.capacity_kwh + TOL)[0]
    if len(over):
        problems.append(f"EV t={over[0]}: stored {energy[over[0]]:.3f} kWh > capacity {params.capacity_kwh} kWh")
    unmet = unmet_energy_kwh(params, day, p, e0_kwh)
    if unmet > TOL:
        problems.append(f"EV: {unmet:.3f} kWh short of the {day.target_kwh:.1f} kWh target at departure "
                        f"(slot {day.departure_slot})")
    return problems


def clip_to_feasible(params: EVParams, day: EVDay, p_ev, e0_kwh: float) -> tuple[np.ndarray, np.ndarray]:
    """Closest possible charging: 0 when away, capped at the charger limit and the battery's free space."""
    p_in = as_profile(p_ev, "p_ev")
    p = np.zeros(SLOTS)
    energy = np.empty(SLOTS + 1)
    energy[0] = e = e0_kwh
    for t in range(SLOTS):
        if day.at_home[t]:
            room_kw = max(params.capacity_kwh - e, 0.0) / (params.eta_charge * DT_H)
            p[t] = min(max(p_in[t], 0.0), params.p_max_kw, room_kw)
        e = e + params.eta_charge * p[t] * DT_H
        if day.arrival_slot is not None and t + 1 == day.arrival_slot:
            e = max(e - day.trip_kwh, 0.0)
        energy[t + 1] = e
    return p, energy
