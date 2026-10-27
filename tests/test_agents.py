"""Tests for M6 (S4 agents): schemas, applying constraints, parsing, and the orchestrator with a scripted LLM."""

import json
from datetime import date

import numpy as np
import pytest
from pydantic import ValidationError

from b2g.agents import tools
from b2g.agents.apply import apply_constraints
from b2g.agents.orchestrator import Orchestrator, extract_json, parse_action, save_trace, until_action
from b2g.agents.schemas import BatteryConstraints, DayConstraints, EVConstraints, PrecoolConstraints, check_hhmm
from b2g.config import load_config
from b2g.models import SLOTS, battery, ev, site, thermal
from b2g.sim.day import Assets, DayData, State, calendar
from b2g.solver.milp import solve_day

CFG = load_config()
ASSETS = Assets.from_config(CFG)
WEDNESDAY, SATURDAY = date(2026, 5, 6), date(2026, 5, 9)
PV = 4.0 * np.clip(np.sin(np.pi * (np.arange(SLOTS) / 4 - 6.5) / 12), 0, None)


def forecast(day=WEDNESDAY, pv=PV):
    price = np.full(SLOTS, 7.0)
    price[36:68] = 5.6
    return DayData(day, price, pv, np.full(SLOTS, 0.5), np.full(SLOTS, 34.0), pv * 250, "forecast:test")


DEMO = EVConstraints(departure_time="07:00", target_soc=0.9), BatteryConstraints(reserve_soc=0.3), \
       PrecoolConstraints(comfort_max_c=26, away_until="14:00")


# --- schemas --------------------------------------------------------------------------------

def test_times_must_be_on_15_minute_steps():
    assert check_hhmm("7:00") == "07:00" and check_hhmm("24:00") == "24:00"
    for bad in ("07:10", "25:00", "seven"):
        with pytest.raises(ValueError):
            check_hhmm(bad)


@pytest.mark.parametrize("model, data", [
    (EVConstraints, {"departure_time": "09:00", "arrival_time": "08:00"}),
    (EVConstraints, {"target_soc": 90}),                       # must be a fraction
    (EVConstraints, {"departure": "07:00"}),                   # unknown field
    (PrecoolConstraints, {"comfort_min_c": 27, "comfort_max_c": 25}),
    (PrecoolConstraints, {"home_all_day": True, "away_from": "09:00"}),
    (BatteryConstraints, {"reserve_soc": 1.5}),
])
def test_invalid_agent_answers_are_rejected(model, data):
    with pytest.raises(ValidationError):
        model.model_validate(data)


def test_changes_lists_only_non_defaults():
    c = DayConstraints(ev=EVConstraints(target_soc=0.9, reasoning="asked for 90 %"))
    assert c.changes() == {"ev": {"target_soc": 0.9}, "battery": {}, "precool": {}}


# --- applying constraints -------------------------------------------------------------------

def test_apply_demo_constraints():
    c = DayConstraints(ev=DEMO[0], battery=DEMO[1], precool=DEMO[2])
    day_assets, notes = apply_constraints(ASSETS, WEDNESDAY, c)
    ev_day, occupied = calendar(day_assets, WEDNESDAY)
    assert notes == []
    assert ev_day.departure_slot == 28 and not ev_day.at_home[28:72].any() and ev_day.at_home[:28].all()
    assert ev_day.target_kwh == pytest.approx(36.0)
    assert day_assets.battery.e_min_kwh == pytest.approx(3.0)
    assert day_assets.thermal.comfort_max_c == 26 and day_assets.thermal.comfort_min_c == 24
    assert occupied[:32].all() and not occupied[32:56].any() and occupied[56:].all()   # home again from 14:00
    assert ASSETS.ev.departure == "08:00"                                              # defaults untouched


def test_apply_weekend_trip_and_home_all_day():
    c = DayConstraints(ev=EVConstraints(departure_time="10:00", arrival_time="16:00"), precool=PrecoolConstraints(home_all_day=True))
    day_assets, _ = apply_constraints(ASSETS, SATURDAY, c)
    ev_day, occupied = calendar(day_assets, SATURDAY)
    assert (ev_day.departure_slot, ev_day.arrival_slot) == (40, 64) and occupied.all()


def test_apply_fixes_and_notes():
    c = DayConstraints(precool=PrecoolConstraints(comfort_max_c=23), battery=BatteryConstraints(reserve_soc=0.05),
                       ev=EVConstraints(skip_charging=True))
    day_assets, notes = apply_constraints(ASSETS, WEDNESDAY, c)
    assert (day_assets.thermal.comfort_min_c, day_assets.thermal.comfort_max_c) == (21, 23)
    assert day_assets.battery.soc_min == ASSETS.battery.soc_min
    assert day_assets.ev.p_max_kw == 0 and calendar(day_assets, WEDNESDAY)[0].target_kwh == 0
    assert len(notes) == 2


def test_no_grid_charging_means_battery_charges_from_surplus_only():
    night_cheap = forecast(pv=np.zeros(SLOTS))
    night_cheap.price[:24] = 1.0                       # tempting to charge from the grid at night
    c = DayConstraints(battery=BatteryConstraints(allow_grid_charging=False))
    day_assets, _ = apply_constraints(ASSETS, WEDNESDAY, c)
    ev_day, occupied = calendar(day_assets, WEDNESDAY)
    plan = solve_day(day_assets, night_cheap, ev_day, occupied, State(1.5, 32.0, 25.0))
    assert plan.actions.p_charge.max() < 1e-6
    allowed = solve_day(ASSETS, night_cheap, *calendar(ASSETS, WEDNESDAY), State(1.5, 32.0, 25.0))
    assert allowed.actions.p_charge.sum() > 0


# --- parsing --------------------------------------------------------------------------------

def test_parse_action_formats():
    assert parse_action("Thought: x\nACTION: GET_FORECAST") == ("GET_FORECAST", {})
    assert parse_action("<think>ACTION: FINISH</think>\n**ACTION:** CALL_AGENT | agent_name=ev_agent | user_request=leave at 7 | car at 90%") == \
        ("CALL_AGENT", {"agent_name": "ev_agent", "user_request": "leave at 7 | car at 90%"})
    assert parse_action("ACTION: FINISH | summary=Car ready by 07:00.\nRoom stays at 26 °C.") == \
        ("FINISH", {"summary": "Car ready by 07:00.\nRoom stays at 26 °C."})
    assert parse_action("I think we should plan.") is None


def test_until_action_drops_invented_observations():
    text = "Thought: get data\nACTION: GET_FORECAST\nObservation: sunny all day\nACTION: RUN_SOLVER"
    assert until_action(text) == "Thought: get data\nACTION: GET_FORECAST"


def test_extract_json_variants():
    assert extract_json('{"target_soc": 0.9}') == {"target_soc": 0.9}
    assert extract_json('Sure:\n```json\n{"reserve_soc": 0.3}\n```') == {"reserve_soc": 0.3}
    assert extract_json('<think>{"x": 1}</think> {"comfort_max_c": 26}') == {"comfort_max_c": 26}
    with pytest.raises(ValueError):
        extract_json("no json here")


# --- orchestrator with a scripted LLM -------------------------------------------------------

class ScriptedLLM:
    """Stands in for LLMClient: answers from scripts per tag and records every request."""

    def __init__(self, orchestrator, agents=None):
        self.scripts = {"s4:orchestrator": list(orchestrator), **{f"s4:{k}": list(v) for k, v in (agents or {}).items()}}
        self.calls = []

    def complete(self, payload, timeout=60, tag=""):
        self.calls.append((tag, payload))
        return {"choices": [{"message": {"content": self.scripts[tag].pop(0)}}], "usage": {"total_tokens": 10}}


DEMO_SCRIPT = [
    "Thought: look at tomorrow first.\nACTION: GET_FORECAST",
    "Thought: and the routine.\nACTION: GET_CALENDAR",
    "Thought: car first.\nACTION: CALL_AGENT | agent_name=ev_agent | user_request=leaving at 7 instead of 8, car at 90%",
    "Thought: cooling.\nACTION: CALL_AGENT | agent_name=precool_agent | user_request=working from home from 2 pm, keep it under 26",
    "Thought: battery.\nACTION: CALL_AGENT | agent_name=battery_agent | user_request=keep at least 30% for power cuts",
    "Thought: solve.\nACTION: RUN_SOLVER",
    "Thought: explain.\nACTION: FINISH | summary=The car will be at 90% by 07:00 and the house stays under 26 °C from 14:00.",
]
DEMO_AGENTS = {
    "ev_agent": ['{"departure_time": "07:00", "target_soc": 0.9, "reasoning": "leaves an hour earlier, needs 90%"}'],
    "precool_agent": ['```json\n{"comfort_max_c": 26, "away_until": "14:00", "reasoning": "home from 14:00"}\n```'],
    "battery_agent": ['{"reserve_soc": 0.3, "reasoning": "30% backup"}'],
}


def test_end_to_end_request_to_schedule(tmp_path):
    llm = ScriptedLLM(DEMO_SCRIPT, DEMO_AGENTS)
    state = State.initial(ASSETS)
    result = Orchestrator(ASSETS, forecast(), state, client=llm, verify=False).run("demo request")
    assert result.success and result.steps == 7 and result.final_summary.startswith("The car will be at 90%")
    assert result.constraints.changes() == {"ev": {"departure_time": "07:00", "target_soc": 0.9},
                                            "battery": {"reserve_soc": 0.3},
                                            "precool": {"comfort_max_c": 26.0, "away_until": "14:00"}}
    # The schedule obeys the person's constraints and all physics
    a, day_assets = result.plan.actions, result.day_assets
    ev_day, occupied = calendar(day_assets, WEDNESDAY)
    assert battery.check(day_assets.battery, a.p_charge, a.p_discharge, state.e_bat_kwh) == []
    assert ev.check(day_assets.ev, ev_day, a.p_ev, state.e_ev_kwh) == []
    assert site.check_import_limit(day_assets.grid, result.plan.grid_import) == []
    assert result.plan.e_ev[28] >= 36.0 - 1e-5                    # 90 % by 07:00
    assert result.plan.e_bat.min() >= 3.0 - 1e-6                  # 30 % reserve kept
    assert result.plan_summary["ev"]["departure"] == "07:00" and result.plan_summary["ev"]["target_met"]
    # Observations are fed back, and the trace is readable
    last_orchestrator_payload = [p for t, p in llm.calls if t == "s4:orchestrator"][-1]
    assert "Observation:" in last_orchestrator_payload["messages"][-1]["content"]
    json_path, md_path = save_trace(result, tmp_path)
    md = md_path.read_text(encoding="utf-8")
    assert "## Step 3: CALL_AGENT" in md and "ev_agent" in md and "Answer to the person" in md
    assert json.loads(json_path.read_text(encoding="utf-8"))["constraints_changed"]["battery"] == {"reserve_soc": 0.3}


def test_agent_gets_one_repair_then_defaults():
    script = ["ACTION: CALL_AGENT | agent_name=ev_agent | user_request=leave 7:10",
              "ACTION: CALL_AGENT | agent_name=battery_agent | user_request=keep some",
              "ACTION: RUN_SOLVER", "ACTION: FINISH | summary=ok"]
    agents = {"ev_agent": ['{"departure_time": "07:10"}', '{"departure_time": "07:15"}'],
              "battery_agent": ["no idea", '{"reserve": 0.3}']}
    llm = ScriptedLLM(script, agents)
    result = Orchestrator(ASSETS, forecast(), State.initial(ASSETS), client=llm, verify=False).run("x")
    ev_call, bat_call = result.trace[0]["agent_call"], result.trace[1]["agent_call"]
    assert [a["valid"] for a in ev_call["attempts"]] == [False, True] and "15-minute" in ev_call["attempts"][0]["error"]
    assert result.constraints.ev.departure_time == "07:15"
    assert bat_call.get("fallback_to_defaults") and result.constraints.battery.reserve_soc is None
    assert "defaults kept" in result.trace[1]["observation"]
    repair_messages = [p for t, p in llm.calls if t == "s4:ev_agent"][1]["messages"]
    assert "not valid" in repair_messages[-1]["content"]


def test_orchestrator_handles_mistakes_and_step_limit():
    script = ["I will just answer directly.",
              "ACTION: FINISH | summary=all done",
              "ACTION: CALL_AGENT | agent_name=heat_pump_agent",
              "ACTION: DANCE",
              "ACTION: GET_FORECAST"]
    result = Orchestrator(ASSETS, forecast(), State.initial(ASSETS), client=ScriptedLLM(script), max_steps=5, verify=False).run("x")
    observations = [e["observation"] for e in result.trace]
    assert "No ACTION found" in observations[0]
    assert "RUN_SOLVER before FINISH" in observations[1]
    assert "Unknown agent" in observations[2] and "Unknown action" in observations[3]
    assert not result.success and result.error == "no FINISH within 5 steps"


def test_forecast_summary_uses_only_the_forecast():
    summary = tools.forecast_summary(forecast(pv=PV * 0.5))
    assert summary["pv_forecast_kwh"] == pytest.approx(round(float((PV * 0.5).sum() * 0.25), 1))
    assert summary["price_per_kwh_by_period"] == ["00:00-09:00: 7", "09:00-17:00: 5.6", "17:00-24:00: 7"]
    assert tools.slots_to_ranges(calendar(ASSETS, WEDNESDAY)[1]) == "00:00-08:00, 18:00-24:00"
