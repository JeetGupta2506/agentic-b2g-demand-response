"""Tests for M7: request facts, the verifier's four check groups, replanning in the orchestrator, and S3."""

import json
from datetime import date

import numpy as np
import pytest

from b2g.agents.apply import apply_constraints
from b2g.agents.orchestrator import Orchestrator
from b2g.agents.schemas import BatteryConstraints, DayConstraints, EVConstraints, PrecoolConstraints
from b2g.baselines.pure_llm import hourly, parse_schedule, plan_s3, s3_context
from b2g.cli import DEMO_REQUEST, demo_truth
from b2g.config import load_config
from b2g.models import SLOTS
from b2g.sim.day import Actions, Assets, DayData, State, calendar
from b2g.sim.simulate import settle
from b2g.solver.milp import solve_day
from b2g.verifier.checks import Issue, Report, check_explanation, check_physics, check_request, check_wishes, observed_values
from b2g.verifier.request_facts import extract_facts

CFG = load_config()
ASSETS = Assets.from_config(CFG)
WEDNESDAY = date(2026, 5, 6)
PV = 4.0 * np.clip(np.sin(np.pi * (np.arange(SLOTS) / 4 - 6.5) / 12), 0, None)


def forecast(t_out=34.0, pv=PV):
    price = np.full(SLOTS, 7.0)
    price[36:68] = 5.6
    t = np.full(SLOTS, float(t_out)) if np.isscalar(t_out) else t_out
    return DayData(WEDNESDAY, price, pv, np.full(SLOTS, 0.5), t, pv * 250, "forecast:test")


def zero_actions():
    z = np.zeros(SLOTS)
    return Actions(z, z.copy(), z.copy(), z.copy())


# --- request facts --------------------------------------------------------------------------

def test_request_facts_from_demo_and_variants():
    demo = extract_facts(DEMO_REQUEST)
    assert {"07:00"} <= demo.all_times() and {"08:00", "14:00"} <= demo.all_times()
    assert demo.fractions == [0.9, 0.3] and demo.temperatures == [26.0]
    other = extract_facts("I'll leave half an hour earlier, want it fully charged, battery only from solar, max 3.7 kW")
    assert other.shifts_min == [-30] and {"full", "solar_only"} <= other.phrases and other.powers_kw == [3.7]
    assert other.times == []                                   # "3.7 kW" is not a time
    assert extract_facts("back at 19:30, keep it below 25 degrees").temperatures == [25.0]
    assert extract_facts("leaving at 6am").times == [{"06:00"}]


# --- request consistency --------------------------------------------------------------------

def test_correct_demo_constraints_pass_the_request_check():
    assert check_request(ASSETS, WEDNESDAY, DEMO_REQUEST, demo_truth()) == []


def test_ignored_time_is_caught():
    wrong = demo_truth().model_copy(update={"ev": EVConstraints(target_soc=0.9)})      # departure 07:00 dropped
    issues = check_request(ASSETS, WEDNESDAY, DEMO_REQUEST, wrong)
    assert len(issues) == 1 and "'at 7'" in issues[0].message and issues[0].severity == "error"


def test_invented_value_is_caught():
    invented = demo_truth().model_copy(update={"ev": EVConstraints(departure_time="07:00", target_soc=0.9, arrival_time="17:00")})
    issues = check_request(ASSETS, WEDNESDAY, DEMO_REQUEST, invented)
    assert [i.message for i in issues] == ["arrival_time 17:00 is not supported by the request"]
    assert issues[0].agent == "ev_agent"


def test_relative_time_and_auto_comfort_min_are_supported():
    c = DayConstraints(ev=EVConstraints(departure_time="07:30"), precool=PrecoolConstraints(comfort_max_c=23, comfort_min_c=21))
    assert check_request(ASSETS, WEDNESDAY, "Leaving half an hour earlier, keep it under 23 degrees", c) == []


def test_wrong_percentage_and_missing_phrase_are_caught():
    c = DayConstraints(ev=EVConstraints(target_soc=0.8))
    messages = [i.message for i in check_request(ASSETS, WEDNESDAY, "car at 95% please, battery only from solar", c)]
    assert any("says 95%" in m for m in messages) and any("solar only" in m for m in messages)
    assert any("target_soc 0.8 is not supported" in m for m in messages)


# --- physics and wishes ---------------------------------------------------------------------

def test_solver_plan_has_no_physics_issues():
    state = State.initial(ASSETS)
    plan = solve_day(ASSETS, forecast(), *calendar(ASSETS, WEDNESDAY), state)
    assert check_physics(ASSETS, forecast(), plan.actions, state) == []


def test_tampered_plan_gives_the_expected_physics_errors():
    a = zero_actions()
    a.p_ev[40] = 3.0                         # car is away at 10:00
    a.p_charge[50] = a.p_discharge[50] = 2.0 # both at once
    a.p_ev[80] = 7.4
    a.p_cool[80] = 1.6
    a.p_charge[80] = 1.0                     # 0.5 + 7.4 + 1.6 + 1.0 > 8 kW at 20:00, no sun
    messages = [i.message for i in check_physics(ASSETS, forecast(), a, State(5.0, 16.0, 26.0))]
    assert any("while the car is away" in m for m in messages)
    assert any("same time" in m for m in messages)
    assert any("grid slot 80" in m and "> limit 8.0" in m for m in messages)


def test_impossible_comfort_is_a_warning_with_the_number_to_disclose():
    hot = forecast(t_out=44.0)
    day_assets, _ = apply_constraints(ASSETS, WEDNESDAY, DayConstraints(precool=PrecoolConstraints(comfort_max_c=24, comfort_min_c=22)))
    plan = solve_day(day_assets, hot, *calendar(day_assets, WEDNESDAY), State(5.0, 32.0, 30.0))
    warnings = check_wishes(day_assets, hot, plan.actions, State(5.0, 32.0, 30.0))
    assert warnings and all(w.severity == "warning" for w in warnings)
    assert warnings[0].key is not None and float(warnings[0].key) > 24


# --- explanation ----------------------------------------------------------------------------

SUMMARY = {"home_battery": {"charged_from": "solar"}}


def test_grounded_explanation_passes():
    times, numbers = observed_values(['{"departure": "07:00", "kwh_at_departure": 36.0, "estimated_electricity_cost": 185.53}'])
    text = "Your car will have 36 kWh (90%) by 07:00. Estimated cost ₹185.53."
    assert check_explanation(text, Report(), SUMMARY, times, numbers + [0.9]) == []


def test_explanation_problems_are_caught():
    report = Report([Issue("wish", "warning", "the room reaches 26.9 degC while someone is home", key="26.9")])
    times, numbers = observed_values(['{"comfort_band_c": [24, 26], "estimated_electricity_cost": 185.53, "max_temp_when_home_c": 26.9}'])
    text = ("All your wishes are met ✅: the room stays at or below 26 °C from 14:00, "
            "the battery charges from the grid at midday, and it costs ₹150.")
    messages = [i.message for i in check_explanation(text, report, SUMMARY, times, numbers)]
    assert any("14:00" in m for m in messages)                       # time never observed
    assert any("₹150" in m for m in messages)                        # invented cost
    assert any("does not tell the person" in m for m in messages)    # 26.9 not mentioned
    assert any("every wish is met" in m for m in messages)
    assert any("from the grid" in m for m in messages)


# --- orchestrator with replanning (scripted LLM) --------------------------------------------

class ScriptedLLM:
    def __init__(self, orchestrator, agents=None):
        self.scripts = {"s4:orchestrator": list(orchestrator), **{f"s4:{k}": list(v) for k, v in (agents or {}).items()}}
        self.calls = []

    def complete(self, payload, timeout=60, tag=""):
        self.calls.append((tag, payload))
        return {"choices": [{"message": {"content": self.scripts[tag].pop(0)}}], "usage": {"total_tokens": 10}}


AGENTS_OK = {"precool_agent": ['{"comfort_max_c": 26, "away_until": "14:00"}'], "battery_agent": ['{"reserve_soc": 0.3}']}


def test_injected_wrong_constraint_is_caught_and_repaired():
    script = ["ACTION: CALL_AGENT | agent_name=ev_agent | user_request=leaving at 7 instead of 8, car at 90%",
              "ACTION: CALL_AGENT | agent_name=precool_agent | user_request=home from 2 pm, under 26",
              "ACTION: CALL_AGENT | agent_name=battery_agent | user_request=keep 30%",
              "ACTION: RUN_SOLVER",
              "ACTION: FINISH | summary=Too early: not verified yet.",
              "ACTION: VERIFY",
              "ACTION: CALL_AGENT | agent_name=ev_agent | user_request=Request: leaving at 7. Problem: 07:00 not used",
              "ACTION: RUN_SOLVER",
              "ACTION: VERIFY",
              "ACTION: FINISH | summary=The car leaves at 07:00 with 36 kWh. The room may reach 26.9 °C while you are home."]
    agents = {"ev_agent": ['{"target_soc": 0.9}', '{"departure_time": "07:00", "target_soc": 0.9}'], **AGENTS_OK}
    result = Orchestrator(ASSETS, forecast(t_out=30.0), State.initial(ASSETS), client=ScriptedLLM(script, agents)).run(DEMO_REQUEST)
    observations = [e["observation"] for e in result.trace]
    assert "VERIFY the latest plan before FINISH" in observations[4]
    first_check = json.loads(observations[5])
    assert not first_check["passed"] and "'at 7'" in first_check["errors"][0] and first_check["replans_left"] == 3
    assert result.success and result.replans == 1 and result.report.passed
    assert result.constraints.changes() == demo_truth().changes()
    assert result.plan.e_ev[28] >= 36 - 1e-5                              # 90 % by the corrected 07:00


def test_replans_are_limited_and_remaining_problems_are_disclosed():
    stubborn = ['{"target_soc": 0.9}'] * 5
    script = (["ACTION: CALL_AGENT | agent_name=ev_agent | user_request=x", "ACTION: RUN_SOLVER", "ACTION: VERIFY"]
              + ["ACTION: CALL_AGENT | agent_name=ev_agent | user_request=x", "ACTION: RUN_SOLVER", "ACTION: VERIFY"] * 3
              + ["ACTION: RUN_SOLVER", "ACTION: FINISH | summary=The car will be ready."])
    result = Orchestrator(ASSETS, forecast(t_out=30.0), State.initial(ASSETS), max_steps=20,
                          client=ScriptedLLM(script, {"ev_agent": stubborn})).run("Leaving at 7 tomorrow, car at 90%")
    assert result.replans == 3 and "No replans left" in result.trace[-2]["observation"]
    assert result.success and "Problems the system could not fix" in result.final_summary and "'at 7'" in result.final_summary


def test_false_explanation_gets_one_rewrite_then_the_generated_fallback():
    script = ["ACTION: RUN_SOLVER", "ACTION: VERIFY",
              "ACTION: FINISH | summary=Everything costs ₹10.",
              "ACTION: FINISH | summary=Still ₹10."]
    result = Orchestrator(ASSETS, forecast(t_out=30.0), State.initial(ASSETS), client=ScriptedLLM(script)).run("Plan tomorrow")
    assert "Your explanation has problems" in result.trace[2]["observation"]
    assert result.success and result.explanation_fallback
    assert result.final_summary.startswith("Here is the plan (generated directly from the verified numbers)")


# --- S3 pure LLM ----------------------------------------------------------------------------

def test_s3_context_and_parsing():
    ctx = s3_context(ASSETS, forecast(), State.initial(ASSETS), DEMO_REQUEST)
    assert len(ctx["hourly_forecast"]["solar_kw"]) == 24 and ctx["request"] == DEMO_REQUEST
    actions = parse_schedule({"ev_kw": [7.4] * 7 + [0] * 17, "ac_kw": [0] * 24, "battery_kw": [-2] * 2 + [3] * 22})
    assert actions.p_ev[:28].min() == 7.4 and actions.p_ev[28:].max() == 0
    assert actions.p_discharge[:8].max() == 2 and actions.p_charge[8:].min() == 3
    with pytest.raises(ValueError):
        parse_schedule({"ev_kw": [1] * 23, "ac_kw": [0] * 24, "battery_kw": [0] * 24})
    assert hourly(np.arange(96.0))[:2] == [1.5, 5.5]


def test_s3_bad_schedule_is_flagged_and_settled():
    class Fake:
        def __init__(self, answers):
            self.answers = answers

        def complete(self, payload, timeout=60, tag=""):
            return {"choices": [{"message": {"content": self.answers.pop(0)}}], "usage": {}}

    greedy = json.dumps({"ev_kw": [7.4] * 24, "ac_kw": [1.6] * 24, "battery_kw": [5] * 24, "reasoning": "charge all"})
    state = State.initial(ASSETS)
    actions, record = plan_s3(ASSETS, forecast(), state, DEMO_REQUEST, client=Fake(["not json", greedy]))
    assert [a["valid"] for a in record["attempts"]] == [False, True]
    truth_assets, _ = apply_constraints(ASSETS, WEDNESDAY, demo_truth())
    from b2g.verifier.checks import verify
    report = verify(ASSETS, truth_assets, forecast(), actions, state)
    assert not report.passed and any("away" in i.message for i in report.errors) and any("limit" in i.message for i in report.errors)
    result = settle(truth_assets, actions, forecast(), state, "S3")
    assert result.metrics["violation"]                   # imports above 8 kW in the evening
    _, fallback = plan_s3(ASSETS, forecast(), state, DEMO_REQUEST, client=Fake(["nope", "still nope"]))
    assert fallback["fallback_do_nothing"]
