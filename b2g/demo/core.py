"""Run one request on one day and collect everything the demo app shows, as plain JSON.

For the request, S4 (agents + solver + verifier) plans on the day-ahead forecast. Then, under the
same constraints, S1 (simple rules) and S5 (perfect knowledge) run too, and all of them are settled on
the ACTUAL day. Optionally S3 (pure LLM) as well. Results go to results/demo/<slug>.json.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from b2g import REPO_ROOT
from b2g.agents.llm_client import LLMClient
from b2g.agents.orchestrator import Orchestrator
from b2g.baselines.pure_llm import plan_s3
from b2g.baselines.rule_based import rule_based_actions
from b2g.config import load_config
from b2g.data.build import load_dataset
from b2g.forecasting.evaluate import load_forecasts
from b2g.sim.day import Assets, State, actual_day, calendar, forecast_day
from b2g.sim.simulate import DayResult, settle
from b2g.solver.milp import solve_day
from b2g.verifier.checks import verify

DEMO_DIR = REPO_ROOT / "results" / "demo"
METRICS = ("electricity_cost", "total_cost", "comfort_dh", "ev_unmet_kwh", "peak_import_kw", "self_consumption_pct",
           "import_kwh", "ac_kwh", "violation")

# Pre-run examples: (title, date, request). Dates are test-period days (forecasts exist for them).
EXAMPLES = [
    ("Early start + work from home", "2026-05-06",
     "Tomorrow I'm leaving at 7 instead of 8 and I need the car at 90%. I'm working from home from 2 pm, "
     "keep it under 26 °C. Keep at least 30% in the battery in case of a power cut."),
    ("Home all day in the heat", "2026-05-13",
     "I'm working from home all day tomorrow, please keep the house at most 25 degrees."),
    ("Weekend trip, car full", "2026-05-09",
     "On Saturday I'm driving to Vadodara at 10, back at 16:00, and I need the car full."),
    ("Monsoon day, solar-only battery", "2026-07-30",
     "Normal office day tomorrow. Charge the home battery only from solar."),
]


def slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")


def _metrics(result: DayResult) -> dict[str, Any]:
    out = {k: (bool(result.metrics[k]) if k == "violation" else round(float(result.metrics[k]), 3)) for k in METRICS}
    out["violations"] = result.violations[:5]
    return out


def _series(result: DayResult, actual, day_assets: Assets) -> dict[str, Any]:
    """The settled day (what really happens), 96 slots (97 for states), for charts."""
    _, occupied = calendar(day_assets, actual.day)
    r = lambda x: [round(float(v), 3) for v in np.asarray(x)]
    a = result.applied
    return {"pv": r(actual.pv_kw), "base": r(actual.base_kw), "ev": r(a.p_ev), "ac": r(a.p_cool),
            "charge": r(a.p_charge), "discharge": r(a.p_discharge), "grid_import": r(result.grid_import),
            "grid_export": r(result.grid_export), "price": r(actual.price), "t_out": r(actual.t_out_c),
            "temps": r(result.temps), "e_bat": r(result.e_bat), "e_ev": r(result.e_ev),
            "occupied": [bool(x) for x in occupied],
            "comfort": [day_assets.thermal.comfort_min_c, day_assets.thermal.comfort_max_c],
            "import_limit_kw": day_assets.grid.import_limit_kw, "battery_min_kwh": day_assets.battery.e_min_kwh,
            "ev_target_kwh": calendar(day_assets, actual.day)[0].target_kwh}


def _trace(result) -> list[dict[str, Any]]:
    """Orchestrator steps in a compact, display-ready form."""
    steps = []
    for e in result.trace:
        thought = e["llm"].split("ACTION:")[0].replace("Thought:", "").strip()
        step = {"step": e["step"], "action": e.get("action", "-"), "params": e.get("params", {}),
                "thought": thought[:600], "observation": str(e.get("observation", ""))[:3000]}
        if "agent_call" in e:
            step["agent"] = e["agent_call"]["agent"]
            step["agent_answer"] = e["agent_call"]["constraints"]
        steps.append(step)
    return steps


def run_example(day_text: str, request: str, title: str = "Custom request", with_s3: bool = False,
                client: LLMClient | None = None) -> dict[str, Any]:
    """Plan `request` for `day_text` with S4, compare with S1 and S5 (and S3), settle all on the actual day."""
    cfg = load_config()
    assets = Assets.from_config(cfg)
    df = load_dataset(REPO_ROOT / cfg["data"]["processed_dir"])
    forecasts = load_forecasts(REPO_ROOT / cfg["forecasting"]["forecasts_file"])
    day = date.fromisoformat(day_text)
    forecast = forecast_day(df, forecasts, day, "lgbm", cfg["systems"]["s2_load_forecaster"])
    actual = actual_day(df, day)
    state = State.initial(assets)

    result = Orchestrator(assets, forecast, state, client=client).run(request)
    out: dict[str, Any] = {"title": title, "date": day_text, "weekday": day.strftime("%A"), "request": request,
                           "ok": result.plan is not None and result.success, "error": result.error,
                           "constraints": result.constraints.changes(),
                           "agent_reasoning": {k: getattr(result.constraints, k).reasoning for k in ("ev", "battery", "precool")},
                           "answer": result.final_summary, "plan_summary": result.plan_summary,
                           "verification": result.report.as_dict() if result.report else None,
                           "replans": result.replans, "explanation_fixed": bool(result.explanation_issues),
                           "trace": _trace(result)}
    if result.plan is None:
        return out

    day_assets = result.day_assets
    ev_day, occupied = calendar(day_assets, day)
    s4 = settle(day_assets, result.plan.actions, actual, state, "S4")
    s1 = settle(day_assets, rule_based_actions(day_assets, actual, state), actual, state, "S1")
    s5 = settle(day_assets, solve_day(day_assets, actual, ev_day, occupied, state).actions, actual, state, "S5")
    out["series"] = _series(s4, actual, day_assets)
    out["comparison"] = {"S1 simple rules": _metrics(s1), "S4 our system": _metrics(s4), "S5 perfect knowledge": _metrics(s5)}
    if with_s3:
        actions, record = plan_s3(assets, forecast, state, request, client=client)
        report = verify(assets, day_assets, forecast, actions, state)
        out["comparison"]["S3 pure LLM"] = _metrics(settle(day_assets, actions, actual, state, "S3"))
        out["s3"] = {"format_ok": not record.get("fallback_do_nothing", False), "errors": len(report.errors),
                     "error_examples": [i.message for i in report.errors[:6]],
                     "warnings": [i.message for i in report.warnings], "reasoning": record.get("reasoning", "")[:800]}
    return out


def save_example(data: dict[str, Any], name: str | None = None) -> Path:
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    path = DEMO_DIR / f"{name or slug(data['title'])}.json"
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    return path


def load_examples() -> list[dict[str, Any]]:
    """Pre-run examples in EXAMPLES order (missing ones skipped), then any saved custom runs."""
    known = [DEMO_DIR / f"{slug(t)}.json" for t, _, _ in EXAMPLES]
    others = sorted(p for p in DEMO_DIR.glob("*.json") if p not in known) if DEMO_DIR.exists() else []
    return [json.loads(p.read_text(encoding="utf-8")) for p in known + others if p.exists()]
