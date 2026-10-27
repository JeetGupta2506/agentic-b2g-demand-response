"""Deterministic verifier for a day plan (plan section 2, M7).

Four groups of checks:
- physics (error):     device limits, EV only when home, import limit, battery reserve, power balance
- wishes (warning):    EV target and comfort band as planned; a warning cannot be fixed by replanning if the
                       wish is physically impossible, so it must instead be disclosed to the person
- request (error):     every explicit number in the request is used by some constraint (not ignored) and every
                       changed constraint is backed by the request (not invented); see request_facts.py
- explanation (error): every number in the final answer appears in what the system observed, unmet wishes
                       are mentioned, and the battery's charging source is not misstated
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np

from b2g.agents.schemas import DayConstraints, minutes
from b2g.models import DT_H, TOL, battery, ev, hhmm_to_slot, site, thermal
from b2g.sim.day import Actions, Assets, DayData, State, calendar
from b2g.verifier.request_facts import _time_candidates, extract_facts, hhmm

MAX_LISTED = 8   # issues per group shown to the LLM (the full list stays in the report)


@dataclass(frozen=True)
class Issue:
    group: str                 # physics | wish | request | explanation
    severity: str              # error = must be fixed; warning = must be disclosed
    message: str
    agent: str | None = None   # the agent that should fix it
    key: str | None = None     # a number the explanation must mention (wish warnings)


@dataclass
class Report:
    issues: list[Issue] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    def as_dict(self) -> dict[str, Any]:
        """Compact form for the LLM: passed, errors (with the agent to ask), warnings to disclose."""
        def listed(items):
            out = [f"[{i.group}] {i.message}" + (f" (ask {i.agent})" if i.agent else "") for i in items[:MAX_LISTED]]
            return out + ([f"... and {len(items) - MAX_LISTED} more"] if len(items) > MAX_LISTED else [])
        return {"passed": self.passed, "errors": listed(self.errors), "warnings_to_tell_the_person": listed(self.warnings)}


# --- physics and wishes ---------------------------------------------------------------------

def _room_temps(assets: Assets, forecast: DayData, actions: Actions, state: State, occupied) -> np.ndarray:
    gains = thermal.heat_gains_kw(assets.thermal, forecast.ghi_wm2, occupied)
    return thermal.simulate(assets.thermal, forecast.t_out_c, gains, actions.p_cool, state.t_room_c)


def check_physics(assets: Assets, forecast: DayData, actions: Actions, state: State) -> list[Issue]:
    """Hard limits of every device and the grid, evaluated on the plan's own (forecast) data."""
    ev_day, occupied = calendar(assets, forecast.day)
    messages = battery.check(assets.battery, actions.p_charge, actions.p_discharge, state.e_bat_kwh)
    messages += [m for m in ev.check(assets.ev, ev_day, actions.p_ev, state.e_ev_kwh) if "short of" not in m]
    temps = _room_temps(assets, forecast, actions, state, occupied)
    messages += [m for m in thermal.check(assets.thermal, temps, occupied, actions.p_cool) if "below the AC" not in m]
    overcooled = np.nonzero((np.asarray(actions.p_cool) > TOL) & (temps[1:] < assets.thermal.t_min_c - TOL))[0]
    if len(overcooled):
        messages.append(f"AC cools the room below its minimum {assets.thermal.t_min_c} degC at slot {overcooled[0]}")
    net = site.net_load_kw(forecast.base_kw, forecast.pv_kw, actions.p_ev, actions.p_cool, actions.p_charge, actions.p_discharge)
    messages += site.check_import_limit(assets.grid, site.grid_flows(net)[0])
    return [Issue("physics", "error", m) for m in messages]


def check_wishes(assets: Assets, forecast: DayData, actions: Actions, state: State) -> list[Issue]:
    """EV target and comfort as planned. Warnings: they may be impossible, but must be told."""
    ev_day, occupied = calendar(assets, forecast.day)
    issues = []
    short = ev.unmet_energy_kwh(assets.ev, ev_day, actions.p_ev, state.e_ev_kwh)
    if short > 0.05:
        have = ev_day.target_kwh - short
        issues.append(Issue("wish", "warning", f"the car will have {have:.1f} kWh at departure "
                            f"{hhmm(ev_day.departure_slot * 15)}, {short:.1f} kWh short of the {ev_day.target_kwh:.1f} kWh target",
                            "ev_agent", f"{have:.1f}"))
    temps = _room_temps(assets, forecast, actions, state, occupied)
    discomfort = thermal.comfort_violation_degree_hours(assets.thermal, temps, occupied)
    if discomfort > 0.05:
        home = temps[1:][occupied]
        room = assets.thermal
        if home.max() > room.comfort_max_c:
            issues.append(Issue("wish", "warning", f"the room reaches {home.max():.1f} degC while someone is home "
                                f"(comfort max {room.comfort_max_c:g} degC), {discomfort:.2f} degC*h outside the band",
                                "precool_agent", f"{home.max():.1f}"))
        if home.min() < room.comfort_min_c:
            issues.append(Issue("wish", "warning", f"the room drops to {home.min():.1f} degC while someone is home "
                                f"(comfort min {room.comfort_min_c:g} degC)", "precool_agent", f"{home.min():.1f}"))
    return issues


# --- request consistency --------------------------------------------------------------------

def _default_times(assets: Assets, day: date) -> dict[str, str | None]:
    """The day's default times per constraint field."""
    ev_day, _ = calendar(assets, day)
    room = assets.thermal
    away = room.weekend_away if day.weekday() in assets.weekend_days else room.weekday_away
    return {"departure_time": hhmm(ev_day.departure_slot * 15) if ev_day.departure_slot is not None else assets.ev.departure,
            "arrival_time": hhmm(ev_day.arrival_slot * 15) if ev_day.arrival_slot is not None else assets.ev.arrival,
            "away_from": (away or {}).get("start", room.weekday_away["start"] if room.weekday_away else "08:00"),
            "away_until": (away or {}).get("end", room.weekday_away["end"] if room.weekday_away else "18:00")}


def check_request(assets: Assets, day: date, request: str, constraints: DayConstraints) -> list[Issue]:
    """Explicit numbers in the request must be used (not ignored); changed values must be backed (not invented)."""
    facts = extract_facts(request)
    defaults = _default_times(assets, day)
    c_ev, c_bat, c_room = constraints.ev, constraints.battery, constraints.precool
    time_fields = {"departure_time": ("ev_agent", c_ev.departure_time), "arrival_time": ("ev_agent", c_ev.arrival_time),
                   "away_from": ("precool_agent", c_room.away_from), "away_until": ("precool_agent", c_room.away_until)}
    used_times = {v for _, v in time_fields.values() if v} | {v for v in defaults.values() if v}
    target = c_ev.target_soc if c_ev.target_soc is not None else assets.ev.target_soc
    reserve = c_bat.reserve_soc if c_bat.reserve_soc is not None else assets.battery.soc_min
    lo = c_room.comfort_min_c if c_room.comfort_min_c is not None else assets.thermal.comfort_min_c
    hi = c_room.comfort_max_c if c_room.comfort_max_c is not None else assets.thermal.comfort_max_c
    issues: list[Issue] = []

    # Ignored: something the person said that no constraint reflects
    for candidates, text in zip(facts.times, facts.time_texts):
        if not candidates & used_times:
            issues.append(Issue("request", "error", f"the request says '{text}' ({' or '.join(sorted(candidates))}) "
                                "but no constraint uses that time", "ev_agent or precool_agent"))
    for frac in facts.fractions:
        if not any(abs(frac - v) < 0.005 for v in (target, reserve)) and not (frac == 1.0 and target == 1.0):
            issues.append(Issue("request", "error", f"the request says {frac:.0%} but neither the car target "
                                f"({target:.0%}) nor the battery reserve ({reserve:.0%}) is {frac:.0%}", "ev_agent or battery_agent"))
    for temp in facts.temperatures:
        if not any(abs(temp - v) < 0.05 for v in (lo, hi)):
            issues.append(Issue("request", "error", f"the request says {temp:g} degC but the comfort band is "
                                f"{lo:g}-{hi:g} degC", "precool_agent"))
    for kw in facts.powers_kw:
        if c_ev.max_power_kw is None or abs(kw - c_ev.max_power_kw) > 0.05:
            issues.append(Issue("request", "error", f"the request says {kw:g} kW but no charging limit is set", "ev_agent"))
    if "solar_only" in facts.phrases and c_bat.allow_grid_charging is not False:
        issues.append(Issue("request", "error", "the request asks for battery charging from solar only, "
                            "but allow_grid_charging is not false", "battery_agent"))
    if "skip_charging" in facts.phrases and not c_ev.skip_charging:
        issues.append(Issue("request", "error", "the request says not to charge the car, but skip_charging is not set", "ev_agent"))
    if "home_all_day" in facts.phrases and not c_room.home_all_day:
        issues.append(Issue("request", "error", "the request says someone is home all day, but home_all_day is not set", "precool_agent"))

    # Invented: a changed value the request does not support
    shifted = {hhmm(minutes(d) + s) for d in defaults.values() if d for s in facts.shifts_min if 0 <= minutes(d) + s <= 1440}
    for name, (agent, value) in time_fields.items():
        if value and value not in facts.all_times() | shifted:
            issues.append(Issue("request", "error", f"{name} {value} is not supported by the request", agent))
    if c_ev.target_soc is not None and not any(abs(c_ev.target_soc - f) < 0.005 for f in facts.fractions) \
            and not (c_ev.target_soc == 1.0 and "full" in facts.phrases):
        issues.append(Issue("request", "error", f"target_soc {c_ev.target_soc:g} is not supported by the request", "ev_agent"))
    if c_bat.reserve_soc is not None and not any(abs(c_bat.reserve_soc - f) < 0.005 for f in facts.fractions):
        issues.append(Issue("request", "error", f"reserve_soc {c_bat.reserve_soc:g} is not supported by the request", "battery_agent"))
    if c_room.comfort_max_c is not None and not any(abs(c_room.comfort_max_c - t) < 0.05 for t in facts.temperatures):
        issues.append(Issue("request", "error", f"comfort_max_c {c_room.comfort_max_c:g} is not supported by the request", "precool_agent"))
    if c_room.comfort_min_c is not None and not any(abs(c_room.comfort_min_c - t) < 0.05 for t in facts.temperatures) \
            and abs(c_room.comfort_min_c - (hi - 2)) > 0.05:
        issues.append(Issue("request", "error", f"comfort_min_c {c_room.comfort_min_c:g} is not supported by the request", "precool_agent"))
    if c_room.home_all_day and "home_all_day" not in facts.phrases:
        issues.append(Issue("request", "error", "home_all_day is not supported by the request", "precool_agent"))
    if c_bat.allow_grid_charging is False and "solar_only" not in facts.phrases:
        issues.append(Issue("request", "error", "allow_grid_charging false is not supported by the request", "battery_agent"))
    if c_bat.allow_grid_charging is True and "grid_charging_ok" not in facts.phrases:
        issues.append(Issue("request", "error", "allow_grid_charging true is not supported by the request", "battery_agent"))
    if c_ev.skip_charging and "skip_charging" not in facts.phrases:
        issues.append(Issue("request", "error", "skip_charging is not supported by the request", "ev_agent"))
    if c_ev.max_power_kw is not None and not any(abs(c_ev.max_power_kw - p) < 0.05 for p in facts.powers_kw):
        issues.append(Issue("request", "error", f"max_power_kw {c_ev.max_power_kw:g} is not supported by the request", "ev_agent"))
    return issues


def verify(base_assets: Assets, day_assets: Assets, forecast: DayData, actions: Actions, state: State,
           request: str | None = None, constraints: DayConstraints | None = None) -> Report:
    """All plan checks; request consistency only when the request and constraints are given."""
    issues = check_physics(day_assets, forecast, actions, state) + check_wishes(day_assets, forecast, actions, state)
    if request is not None and constraints is not None:
        issues += check_request(base_assets, forecast.day, request, constraints)
    return Report(issues)


# --- explanation grounding ------------------------------------------------------------------

_TIME = re.compile(r"\b(\d{1,2}):(\d{2})\b|\b(\d{1,2})\s*(am|pm|a\.m\.|p\.m\.)", re.I)
_UNIT_NUMBER = re.compile(r"(?:₹|rs\.?|inr)\s*(\d+(?:[.,]\d+)?)|(\d+(?:\.\d+)?)\s*(%|°\s*c?|degrees?|kwh|kw\b|inr|rupees)", re.I)
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
_OVERCLAIM = re.compile(r"all (?:of )?your (?:wishes|requests)|everything you asked|all wishes|fully met|every wish", re.I)
_GRID_BATTERY = re.compile(r"battery[^.\n]{0,80}\bfrom the grid\b|\bgrid\b[^.\n]{0,40}\bcharg\w*[^.\n]{0,30}\bbattery", re.I)


def observed_values(texts: list[str]) -> tuple[set[str], list[float]]:
    """All 'HH:MM' times and numbers in the given texts (observations, request) - what the LLM may cite."""
    joined = "\n".join(texts)
    times = {f"{int(h):02d}:{m}" for h, m in re.findall(r"\b(\d{1,2}):(\d{2})\b", joined)}
    for candidates in extract_facts(joined).times:
        times |= candidates
    return times, [float(x) for x in _NUMBER.findall(joined.replace(",", ""))]


def check_explanation(text: str, report: Report, plan_summary: dict[str, Any] | None,
                      allowed_times: set[str], allowed_numbers: list[float]) -> list[Issue]:
    """The final answer may only cite observed numbers, must disclose wish warnings, and must not overclaim."""
    issues = []
    for m in _TIME.finditer(text):
        candidates = {f"{int(m.group(1)):02d}:{m.group(2)}"} if m.group(1) else _time_candidates(int(m.group(3)), 0, m.group(4))
        if not candidates & (allowed_times | ({"24:00", "00:00"} if candidates & {"24:00", "00:00"} else set())):
            issues.append(Issue("explanation", "error", f"mentions {m.group(0).strip()}, which appears nowhere in the plan"))
    for m in _UNIT_NUMBER.finditer(text):
        value = float((m.group(1) or m.group(2)).replace(",", "."))
        unit = (m.group(3) or "INR").lower()
        candidates = [value / 100] if unit == "%" else []
        ok = any(abs(value - n) <= max(0.06, 0.01 * abs(n)) for n in allowed_numbers) or \
            any(abs(c - n) < 0.006 for c in candidates for n in allowed_numbers)
        if not ok:
            issues.append(Issue("explanation", "error", f"mentions {m.group(0).strip()}, which appears nowhere in the plan"))
    for warning in report.warnings:
        if warning.key and not any(abs(float(warning.key) - float(n)) <= 0.051 for n in _NUMBER.findall(text)):
            issues.append(Issue("explanation", "error", f"does not tell the person that {warning.message}"))
    if report.warnings and _OVERCLAIM.search(text):
        issues.append(Issue("explanation", "error", "claims every wish is met, but some are not"))
    charged_from = ((plan_summary or {}).get("home_battery") or {}).get("charged_from")
    if charged_from == "solar" and _GRID_BATTERY.search(text):
        issues.append(Issue("explanation", "error", "says the battery charges from the grid, but the plan charges it from solar"))
    return issues


def fallback_explanation(plan_summary: dict[str, Any], report: Report) -> str:
    """Plain explanation generated from the verified plan numbers (used if the LLM's answer fails twice)."""
    ev_s, room, bat = plan_summary["ev"], plan_summary["room"], plan_summary["home_battery"]
    lines = ["Here is the plan (generated directly from the verified numbers):"]
    if ev_s["departure"] != "no trip":
        lines.append(f"- Car: charging {ev_s['charging']}; {ev_s['kwh_at_departure']} kWh of the {ev_s['target_kwh']} kWh "
                     f"target at departure {ev_s['departure']}" + (" (target met)." if ev_s["target_met"] else " (target NOT met)."))
    else:
        lines.append(f"- Car: no trip planned; charging {ev_s['charging']}.")
    lines.append(f"- Room: comfort {room['comfort_band_c'][0]:g}-{room['comfort_band_c'][1]:g} °C while someone is home "
                 f"({room['someone_home']}); AC on {room['ac_on']}; warmest while home {room['max_temp_when_home_c']} °C.")
    lines.append(f"- Battery: reserve {bat['reserve_kwh']} kWh; charging {bat['charging']} (from {bat['charged_from']}); "
                 f"discharging {bat['discharging']}.")
    lines.append(f"- Estimated electricity cost: {plan_summary['estimated_electricity_cost']}.")
    for issue in report.issues:
        lines.append(f"- Note: {issue.message}.")
    return "\n".join(lines)
