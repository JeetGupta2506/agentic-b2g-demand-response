"""S3: the LLM schedules all loads itself from the forecast (no agents, no solver, no verifier).

It shows the failure mode the hybrid design avoids (plan section 5). The LLM gets hourly values
(24 per series; 96 x 3 numbers per day would be an unfair amount to produce) and answers with hourly
EV, AC and battery powers, which are repeated over each hour's four 15-min slots. One retry if the
format is wrong; otherwise an all-zero schedule ("do nothing") is used and flagged.
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np

from b2g.agents.llm_client import LLMClient, get_client
from b2g.agents.orchestrator import PROMPTS_DIR, extract_json, strip_think
from b2g.agents.tools import calendar_info
from b2g.sim.day import Actions, Assets, DayData, State

HOURS = 24
FIELDS = ("ev_kw", "ac_kw", "battery_kw")


def hourly(values) -> list[float]:
    """96 slots -> 24 hourly means, rounded for the prompt."""
    return [round(float(x), 2) for x in np.asarray(values, dtype=float).reshape(HOURS, 4).mean(axis=1)]


def s3_context(assets: Assets, forecast: DayData, state: State, request: str) -> dict[str, Any]:
    """Everything the pure-LLM scheduler is told (forecast only, never actual data)."""
    car, bat, room, grid = assets.ev, assets.battery, assets.thermal, assets.grid
    return {
        "request": request,
        "routine_and_defaults": calendar_info(assets, forecast.day),
        "devices": {
            "battery": {"capacity_kwh": bat.capacity_kwh, "min_kwh": bat.e_min_kwh, "max_charge_kw": bat.p_charge_max_kw,
                        "max_discharge_kw": bat.p_discharge_max_kw, "charge_efficiency": bat.eta_charge,
                        "discharge_efficiency": bat.eta_discharge},
            "ev": {"capacity_kwh": car.capacity_kwh, "charger_max_kw": car.p_max_kw, "charge_efficiency": car.eta_charge,
                   "trip_kwh": car.trip_kwh},
            "ac": {"max_kw": room.p_cool_max_kw, "cop": room.cop},
            "room_model": {"equation": "T_next = T + 0.25/C * ((T_out - T)/R + gains - COP * ac_kw) per 15 min",
                           "R_degC_per_kw": room.r_c_per_kw, "C_kwh_per_degC": room.c_kwh_per_c,
                           "gains_kw": "1.5 * solar_wm2/1000 + 0.3 when someone is home"},
            "grid": {"import_limit_kw": grid.import_limit_kw, "export_credit_per_kwh": grid.export_price},
        },
        "start_state": {"battery_kwh": round(state.e_bat_kwh, 2), "ev_kwh": round(state.e_ev_kwh, 2),
                        "room_c": round(state.t_room_c, 2)},
        "hourly_forecast": {"solar_kw": hourly(forecast.pv_kw), "base_load_kw": hourly(forecast.base_kw),
                            "outdoor_c": hourly(forecast.t_out_c), "solar_wm2": hourly(forecast.ghi_wm2),
                            "price_per_kwh": hourly(forecast.price)},
    }


def parse_schedule(answer: dict[str, Any]) -> Actions:
    """{"ev_kw": [24], "ac_kw": [24], "battery_kw": [24]} -> 96-slot Actions (battery split into charge/discharge)."""
    series = {}
    for name in FIELDS:
        values = answer.get(name)
        if not isinstance(values, list) or len(values) != HOURS:
            raise ValueError(f"'{name}' must be a list of {HOURS} numbers")
        try:
            series[name] = np.repeat(np.asarray(values, dtype=float), 4)
        except (TypeError, ValueError):
            raise ValueError(f"'{name}' must contain only numbers") from None
    battery = series["battery_kw"]
    return Actions(np.clip(battery, 0, None), np.clip(-battery, 0, None), series["ev_kw"], series["ac_kw"])


def plan_s3(assets: Assets, forecast: DayData, state: State, request: str,
            client: LLMClient | None = None) -> tuple[Actions, dict[str, Any]]:
    """One LLM call (+1 format retry). Returns the actions and a record for the trace."""
    client = client or get_client()
    messages = [{"role": "system", "content": (PROMPTS_DIR / "pure_llm.md").read_text(encoding="utf-8")},
                {"role": "user", "content": json.dumps(s3_context(assets, forecast, state, request))}]
    record: dict[str, Any] = {"attempts": []}
    for _ in range(2):
        result = client.complete({"messages": messages, "max_tokens": 6000}, timeout=180, tag="s3:scheduler")
        answer = result["choices"][0]["message"].get("content") or ""
        try:
            parsed = extract_json(answer)
            actions = parse_schedule(parsed)
            record["attempts"].append({"valid": True, "answer": strip_think(answer)[:4000]})
            record["reasoning"] = parsed.get("reasoning", "")
            return actions, record
        except ValueError as e:
            record["attempts"].append({"valid": False, "error": str(e), "answer": strip_think(answer)[:4000]})
            messages += [{"role": "assistant", "content": strip_think(answer)},
                         {"role": "user", "content": f"Your answer was not valid: {e}. Answer again with the JSON object only."}]
    record["fallback_do_nothing"] = True
    zero = np.zeros(96)
    return Actions(zero, zero, zero, zero), record
