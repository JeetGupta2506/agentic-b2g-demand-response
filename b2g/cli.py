"""Headless runner: run a system on one request and save a JSON summary.

    python -m b2g.cli --system S0 --request "Schedule all flexible loads for minimal cost"
    python -m b2g.cli --provider openrouter --model <id>      # same task, other provider
    python -m b2g.cli --cache off                             # force fresh LLM answers
    python -m b2g.cli --system S4 --date 2026-05-06 --request "I'm leaving at 7 tomorrow ..."

Outputs in results/runs/<run_id>/: llm_calls.jsonl (every LLM call) and summary.json;
S4 also writes trace.md / trace.json (the agents' reasoning) and settles its plan on the actual day.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from dataclasses import replace
from datetime import date, datetime
from typing import Any, Sequence

from b2g.agents import llm_client
from b2g.agents.llm_client import CACHE_MODES, PROVIDER_BASE_URLS, REPO_ROOT, LLMClient, LLMSettings

SYSTEMS = ("S0", "S3", "S4")
DEFAULT_REQUEST = "Schedule all flexible loads for minimal cost"
DEMO_REQUEST = ("Tomorrow I'm leaving at 7 instead of 8 and I need the car at 90%. I'm working from home from 2 pm, "
                "keep it under 26 °C. Keep at least 30% in the battery in case of a power cut.")
DEMO_DATE = "2026-05-06"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Command-line options."""
    parser = argparse.ArgumentParser(prog="python -m b2g.cli", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--system", choices=SYSTEMS, default="S0",
                        help="S0 = base paper (original orchestrator); S3 = pure LLM; S4 = our agents + solver + verifier")
    parser.add_argument("--request", help="natural-language request (default depends on the system)")
    parser.add_argument("--date", default=DEMO_DATE, help="S3/S4: day to plan (needs forecasts, i.e. a val/test day)")
    parser.add_argument("--pv-forecaster", default="lgbm", choices=("lgbm", "physics"), help="S3/S4: PV forecast to plan with")
    parser.add_argument("--no-verify", action="store_true", help="S4 without the M7 verifier (as in M6)")
    parser.add_argument("--provider", choices=sorted(PROVIDER_BASE_URLS), help="override LLM_PROVIDER from .env")
    parser.add_argument("--model", help="override the provider's model from .env")
    parser.add_argument("--cache", choices=CACHE_MODES, default="on",
                        help="on: reuse cached answers; off: never cache; refresh: ask again and overwrite")
    parser.add_argument("--run-id", help="name of the output folder in results/runs/ (default: timestamp_system)")
    args = parser.parse_args(argv)
    if args.request is None:
        args.request = DEMO_REQUEST if args.system in ("S3", "S4") else DEFAULT_REQUEST
    return args


def demo_truth():
    """The intended reading of DEMO_REQUEST (ground truth for judging S3 and S4 on the demo)."""
    from b2g.agents.schemas import BatteryConstraints, DayConstraints, EVConstraints, PrecoolConstraints

    return DayConstraints(ev=EVConstraints(departure_time="07:00", target_soc=0.9), battery=BatteryConstraints(reserve_soc=0.3),
                          precool=PrecoolConstraints(comfort_max_c=26, away_until="14:00"))


def _day_inputs(args: argparse.Namespace):
    """Config, assets, the forecast (what the planner sees) and the actual day for args.date."""
    from b2g.config import load_config
    from b2g.data.build import load_dataset
    from b2g.forecasting.evaluate import load_forecasts
    from b2g.sim.day import Assets, actual_day, forecast_day

    cfg = load_config()
    df = load_dataset(REPO_ROOT / cfg["data"]["processed_dir"])
    forecasts = load_forecasts(REPO_ROOT / cfg["forecasting"]["forecasts_file"])
    day = date.fromisoformat(args.date)
    forecast = forecast_day(df, forecasts, day, args.pv_forecaster, cfg["systems"]["s2_load_forecaster"])
    return cfg, Assets.from_config(cfg), forecast, actual_day(df, day)


def run_s3(args: argparse.Namespace, settings: LLMSettings) -> dict[str, Any]:
    """Pure-LLM schedule, verified and settled under the request's true constraints (demo) or the defaults."""
    from b2g.agents.apply import apply_constraints
    from b2g.agents.schemas import DayConstraints
    from b2g.baselines.pure_llm import plan_s3
    from b2g.sim.day import State
    from b2g.sim.simulate import settle
    from b2g.verifier.checks import verify

    _, assets, forecast, actual = _day_inputs(args)
    state = State.initial(assets)
    truth = demo_truth() if args.request == DEMO_REQUEST else DayConstraints()
    truth_assets, _ = apply_constraints(assets, forecast.day, truth)
    actions, record = plan_s3(assets, forecast, state, args.request)
    report = verify(assets, truth_assets, forecast, actions, state)
    settled = settle(truth_assets, actions, actual, state, "S3")
    out_dir = settings.results_dir / "runs" / settings.run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "s3_answer.json").write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "run_id": settings.run_id, "system": "S3", "request": args.request, "date": args.date,
        "provider": settings.provider, "model": settings.model, "pv_forecaster": args.pv_forecaster,
        "judged_against": "demo ground truth" if args.request == DEMO_REQUEST else "defaults (no ground truth for this request)",
        "format_ok": not record.get("fallback_do_nothing", False), "llm_reasoning": record.get("reasoning", ""),
        "verification": {"passed": report.passed, "errors": [i.message for i in report.errors],
                         "warnings": [i.message for i in report.warnings]},
        "actual_outcome": settled.metrics, "actual_violations": settled.violations,
        "llm": llm_client.get_client().stats.as_dict(),
    }


def configure_llm(args: argparse.Namespace) -> LLMSettings:
    """
    Resolve provider/model from .env plus CLI overrides and install the shared client.
    The original orchestrator reads its model from CEREBRAS_MODEL_OVERRIDE, so it is set too.
    """
    llm_client.load_env()
    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    run_id = args.run_id or f"{datetime.now():%Y%m%d_%H%M%S}_{args.system}"
    os.environ["LLM_CACHE"] = args.cache
    os.environ["LLM_RUN_ID"] = run_id
    settings = LLMSettings.from_env()
    if args.model:
        settings = replace(settings, model=args.model)
    os.environ["CEREBRAS_MODEL_OVERRIDE"] = settings.model
    llm_client.set_client(LLMClient(settings))
    return settings


def run_s0(request: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run the base paper's orchestrator; return its result and its working context (prices, schedules)."""
    from orchestrator_agent_react import OrchestratorAgentReAct

    class RecordingOrchestrator(OrchestratorAgentReAct):
        """Keeps a reference to the context so partial schedules survive a failed run."""

        context: dict[str, Any] = {}

        def _execute_action(self, action, context):
            self.context = context
            return super()._execute_action(action, context)

    orchestrator = RecordingOrchestrator()
    try:
        result = orchestrator.run_scheduling(request)
    except Exception as e:  # keep the summary (and partial schedules) even if the original crashes
        print(f"\n[b2g.cli] Orchestrator crashed: {type(e).__name__}: {e}")
        result = {"success": False, "error": f"{type(e).__name__}: {e}"}
    return result, orchestrator.context


def start_slots(executed_schedules: list[dict[str, Any]]) -> dict[str, int]:
    """First ON slot (0-95, 15-min slots) of each scheduled appliance's 96-slot on/off array."""
    return {s["appliance_id"]: s["schedule"].index(1) for s in executed_schedules if 1 in s["schedule"]}


def optimal_start_slots(prices: list[float]) -> dict[str, int]:
    """Optimal start slots from milp-baseline/optimizer.py (EV ready by 07:00, the original default)."""
    spec = importlib.util.spec_from_file_location("milp_optimizer", REPO_ROOT / "milp-baseline" / "optimizer.py")
    optimizer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(optimizer)
    return {name: r["optimal_slot"] for name, r in optimizer.optimize_all_appliances(prices).items()}


def build_summary(args: argparse.Namespace, settings: LLMSettings, result: dict[str, Any],
                  context: dict[str, Any], stats: dict[str, Any]) -> dict[str, Any]:
    """Everything needed to compare runs: what was asked, what was scheduled, cost in tokens/time."""
    slots = start_slots(context.get("executed_schedules", []))
    prices = (context.get("prices_data") or {}).get("prices")
    optimal = optimal_start_slots(prices) if prices else None
    usage = result.get("total_usage", {})
    return {
        "run_id": settings.run_id,
        "system": args.system,
        "request": args.request,
        "provider": settings.provider,
        "base_url": settings.base_url,
        "model": settings.model,
        "cache_mode": settings.cache_mode,
        "success": result.get("success", False),
        "error": result.get("error"),
        "iterations": result.get("iterations"),
        "duration_s": round(result.get("duration_seconds", 0) or 0, 2),
        "prices_date": (context.get("prices_data") or {}).get("date"),
        "start_slots": slots,
        "optimal_start_slots": optimal,
        "matches_optimizer": optimal is not None and slots == optimal,
        "missing_appliances": sorted(set(optimal or {}) - set(slots)),
        "orchestrator_tokens": usage.get("total_tokens"),
        "llm": stats,
    }


def _slot_time(slot: int) -> str:
    """15-min slot index -> HH:MM."""
    return f"{slot * 15 // 60:02d}:{slot * 15 % 60:02d}"


def print_summary(summary: dict[str, Any]) -> None:
    """Short human-readable report."""
    llm = summary["llm"]
    print("\n" + "=" * 80)
    print(f"B2G CLI SUMMARY  {summary['system']}  {summary['provider']} / {summary['model']}")
    print("=" * 80)
    optimal = summary["optimal_start_slots"] or {}
    for name in sorted(set(optimal) | set(summary["start_slots"])):
        got, best = summary["start_slots"].get(name), optimal.get(name)
        got_text = f"{_slot_time(got)} (slot {got})" if got is not None else "not scheduled"
        best_text = f"{_slot_time(best)} (slot {best})" if best is not None else "-"
        print(f"  {name:16} LLM {got_text:22} optimizer {best_text:20} {'✓' if got == best else '✗'}")
    print(f"  Matches optimizer: {summary['matches_optimizer']}   Success: {summary['success']}")
    print(f"  LLM calls: {llm['calls']} ({llm['cache_hits']} from cache, {llm['api_calls']} to provider)")
    print(f"  Tokens spent: {llm['prompt_tokens_spent'] + llm['completion_tokens_spent']}   "
          f"LLM time: {llm['latency_s']} s   Run time: {summary['duration_s']} s")
    print(f"  Saved: results/runs/{summary['run_id']}/summary.json")
    print("=" * 80)


def run_s4(args: argparse.Namespace, settings: LLMSettings) -> dict[str, Any]:
    """Agents + solver plan the day on forecasts; the plan is then settled on the actual day."""
    from b2g.agents.orchestrator import Orchestrator, save_trace
    from b2g.sim.day import State
    from b2g.sim.simulate import settle

    _, assets, forecast, actual = _day_inputs(args)
    state = State.initial(assets)

    result = Orchestrator(assets, forecast, state, verify=not args.no_verify).run(args.request)
    out_dir = settings.results_dir / "runs" / settings.run_id
    _, trace_md = save_trace(result, out_dir)
    settled = settle(result.day_assets, result.plan.actions, actual, state, "S4") if result.plan else None
    return {
        "run_id": settings.run_id, "system": "S4" + (" (no verifier)" if args.no_verify else ""),
        "request": args.request, "date": args.date,
        "constraints_match_demo_truth": (result.constraints.changes() == demo_truth().changes()) if args.request == DEMO_REQUEST else None,
        "verification": result.report.as_dict() if result.report else None, "replans": result.replans,
        "explanation_issues_caught": result.explanation_issues, "explanation_fallback": result.explanation_fallback,
        "provider": settings.provider, "model": settings.model, "cache_mode": settings.cache_mode,
        "pv_forecaster": args.pv_forecaster, "success": result.success, "error": result.error, "steps": result.steps,
        "constraints_changed": result.constraints.changes(), "plan_summary": result.plan_summary,
        "final_summary": result.final_summary,
        "actual_outcome": settled.metrics if settled else None,
        "actual_violations": settled.violations if settled else None,
        "trace": str(trace_md.relative_to(REPO_ROOT)),
        "llm": llm_client.get_client().stats.as_dict(),
    }


def print_s4_summary(summary: dict[str, Any]) -> None:
    """Short human-readable report for S4."""
    llm, outcome = summary["llm"], summary["actual_outcome"] or {}
    print("\n" + "=" * 80)
    print(f"B2G CLI SUMMARY  S4  {summary['date']}  {summary['provider']} / {summary['model']}")
    print("=" * 80)
    print(f"  Finished: {summary['success']} in {summary['steps']} steps" + (f" ({summary['error']})" if summary["error"] else ""))
    print(f"  Constraints from the request: {json.dumps(summary['constraints_changed'])}"
          + (f"  (match demo truth: {summary['constraints_match_demo_truth']})" if summary["constraints_match_demo_truth"] is not None else ""))
    if summary["verification"] is not None:
        print(f"  Verifier: {json.dumps(summary['verification'], ensure_ascii=False)}  replans: {summary['replans']}")
        if summary["explanation_issues_caught"]:
            print(f"  Explanation problems caught: {summary['explanation_issues_caught']} "
                  f"(generated fallback used: {summary['explanation_fallback']})")
    if outcome:
        print(f"  On the actual day: electricity {outcome['electricity_cost']:.2f}, discomfort {outcome['comfort_dh']:.2f} degC*h, "
              f"EV short {outcome['ev_unmet_kwh']:.2f} kWh, peak {outcome['peak_import_kw']:.2f} kW, "
              f"violations: {summary['actual_violations'] or 'none'}")
    print(f"  LLM calls: {llm['calls']} ({llm['cache_hits']} from cache)   Tokens spent: "
          f"{llm['prompt_tokens_spent'] + llm['completion_tokens_spent']}   LLM time: {llm['latency_s']} s")
    print(f"  Answer to the person: {summary['final_summary'][:600]}")
    print(f"  Trace: {summary['trace']}")
    print("=" * 80)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Exit code 0 if the run finished (even if it differs from the optimizer)."""
    args = parse_args(argv)
    settings = configure_llm(args)
    print(f"[b2g.cli] {args.system} via {settings.provider} ({settings.base_url}), model {settings.model}, "
          f"cache {settings.cache_mode}, run {settings.run_id}")

    if args.system in ("S3", "S4"):
        summary = run_s4(args, settings) if args.system == "S4" else run_s3(args, settings)
        out_dir = settings.results_dir / "runs" / settings.run_id
        (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        if args.system == "S4":
            print_s4_summary(summary)
        else:
            print(json.dumps({k: summary[k] for k in ("system", "model", "judged_against", "format_ok", "verification",
                                                      "actual_violations")}, indent=1, ensure_ascii=False)[:3000])
            outcome = summary["actual_outcome"]
            print(f"On the actual day: electricity {outcome['electricity_cost']:.2f}, discomfort {outcome['comfort_dh']:.2f} degC*h, "
                  f"EV short {outcome['ev_unmet_kwh']:.2f} kWh, peak {outcome['peak_import_kw']:.2f} kW")
        return 0 if summary.get("success", summary.get("format_ok")) else 1

    result, context = run_s0(args.request)
    summary = build_summary(args, settings, result, context, llm_client.get_client().stats.as_dict())
    out_dir = settings.results_dir / "runs" / settings.run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print_summary(summary)
    return 0 if summary["success"] else 1


if __name__ == "__main__":
    # The original reads its prompt .md files and prints ✓/⚠ with the default encoding, which is
    # cp1252 on Windows and crashes; restart once in Python's UTF-8 mode instead of requiring PYTHONUTF8=1.
    if not sys.flags.utf8_mode:
        sys.exit(subprocess.call([sys.executable, "-X", "utf8", "-m", "b2g.cli", *sys.argv[1:]]))
    sys.exit(main())
