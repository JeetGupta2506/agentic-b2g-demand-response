"""M5: compare S1 (rules), S2 (forecast + MILP, one run per PV forecaster) and S5 (oracle) on test days.

    python -m b2g.eval.compare_baselines            # days from b2g/config/default.yaml (evaluation)
    python -m b2g.eval.compare_baselines --start 2026-07-06 --days 7

Every system is settled on ACTUAL data and carries its own actual end state into the next day.
Writes results/m5_baselines.csv (per day) and .md (averages + acceptance), results/figures/m5_oracle_day.png.
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd

from b2g import REPO_ROOT
from b2g.baselines import forecast_milp, rule_based
from b2g.config import load_config
from b2g.data.build import load_dataset
from b2g.forecasting.evaluate import load_forecasts
from b2g.models import DT_H
from b2g.sim.day import Assets, actual_day, forecast_day
from b2g.sim.simulate import DayResult, run_days

COLUMNS = ["total_cost", "electricity_cost", "battery_wear_cost", "comfort_dh", "ev_unmet_kwh", "peak_import_kw",
           "self_consumption_pct", "import_kwh", "export_kwh", "ac_kwh", "ev_kwh", "violation"]


def run_all(cfg: dict[str, Any], start: date, n_days: int) -> dict[str, list[DayResult]]:
    """Run every system over the same days."""
    assets = Assets.from_config(cfg)
    df = load_dataset(REPO_ROOT / cfg["data"]["processed_dir"])
    forecasts = load_forecasts(REPO_ROOT / cfg["forecasting"]["forecasts_file"])
    actual_for = lambda d: actual_day(df, d)
    systems = {"S1 rules": rule_based.make_system(assets, actual_for, cfg["systems"]["s1_ev_respects_grid_limit"])}
    for pv_model in cfg["systems"]["s2_pv_forecasters"]:
        load_model = cfg["systems"]["s2_load_forecaster"]
        systems[f"S2 MILP (pv={pv_model})"] = forecast_milp.make_planner(
            assets, lambda d, m=pv_model: forecast_day(df, forecasts, d, m, load_model))
    systems["S5 oracle"] = forecast_milp.make_planner(assets, actual_for)
    return {name: run_days(assets, name, system, actual_for, start, n_days) for name, system in systems.items()}


def results_table(results: dict[str, list[DayResult]]) -> pd.DataFrame:
    """One row per (system, day)."""
    rows = [{"system": name, "date": r.day.isoformat(), **{c: r.metrics[c] for c in COLUMNS},
             "violations": "; ".join(r.violations[:3])} for name, days in results.items() for r in days]
    return pd.DataFrame(rows)


def acceptance(table: pd.DataFrame) -> dict[str, Any]:
    """M5 check: oracle has no violations and mean total cost oracle <= every S2 <= S1."""
    mean = table.groupby("system")["total_cost"].mean()
    s2 = [s for s in mean.index if s.startswith("S2")]
    return {
        "oracle_violation_days": int(table.loc[table["system"] == "S5 oracle", "violation"].sum()),
        "oracle_le_s2": bool(all(mean["S5 oracle"] <= mean[s] + 1e-6 for s in s2)),
        "s2_le_s1": {s: bool(mean[s] <= mean["S1 rules"] + 1e-6) for s in s2},
    }


def to_markdown(table: pd.DataFrame, check: dict[str, Any], start: date, n_days: int) -> str:
    """Averages per system plus the acceptance result."""
    agg = table.groupby("system", sort=False).agg(
        total=("total_cost", "mean"), electricity=("electricity_cost", "mean"), wear=("battery_wear_cost", "mean"),
        comfort=("comfort_dh", "mean"), ev_unmet=("ev_unmet_kwh", "mean"), peak=("peak_import_kw", "mean"),
        selfc=("self_consumption_pct", "mean"), viol=("violation", "sum"))
    lines = [f"# M5 baselines — {n_days} test days from {start}", "",
             "Settled on actual data. Money in INR per day (placeholder tariff). Total = electricity + battery wear"
             " + comfort penalty + EV-shortfall penalty.", "",
             "| System | Total cost | Electricity | Battery wear | Discomfort °C·h | EV short kWh | Peak kW | Self-consumption % | Violation days |",
             "|---|---|---|---|---|---|---|---|---|"]
    for name, r in agg.iterrows():
        lines.append(f"| {name} | {r.total:.2f} | {r.electricity:.2f} | {r.wear:.2f} | {r.comfort:.2f} | {r.ev_unmet:.2f} "
                     f"| {r.peak:.2f} | {r.selfc:.1f} | {int(r.viol)}/{n_days} |")
    lines += ["", "## Acceptance", "",
              f"- Oracle violation days: {check['oracle_violation_days']}",
              f"- Oracle ≤ every S2 (mean total cost): {check['oracle_le_s2']}",
              *[f"- {s} ≤ S1 (mean total cost): {ok}" for s, ok in check["s2_le_s1"].items()], ""]
    return "\n".join(lines)


def plot_day(result: DayResult, actual_pv: np.ndarray, base: np.ndarray, assets: Assets, path: Path) -> Path:
    """Stacked loads vs PV, grid exchange and room temperature for one settled day."""
    import matplotlib.pyplot as plt

    from b2g.data.plots import GRID, TEXT, _save, _style

    _style()
    hours = np.arange(96) * DT_H
    a = result.applied
    fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True, gridspec_kw={"height_ratios": [3, 2, 2]})
    loads = [("Base load", base, "#2a78d6"), ("AC", a.p_cool, "#eb6834"), ("EV", a.p_ev, "#1baf7a"),
             ("Battery charging", a.p_charge, "#eda100")]
    axes[0].stackplot(hours, *[x for _, x, _ in loads], labels=[n for n, _, _ in loads], colors=[c for _, _, c in loads],
                      step="post", edgecolor="#fcfcfb", linewidth=0.5)
    axes[0].step(hours, actual_pv, where="post", color=TEXT, linewidth=1.6, label="PV (actual)")
    axes[0].step(hours, a.p_discharge, where="post", color="#e87ba4", linewidth=1.4, label="Battery discharging")
    axes[0].set_title(f"{result.system}, {result.day:%a %d %b %Y}: where the power goes")
    axes[0].set_ylabel("kW")
    axes[0].legend(loc="lower right", bbox_to_anchor=(1, 1), ncol=3, fontsize=8)

    axes[1].step(hours, result.grid_import, where="post", color="#2a78d6", label="Grid import")
    axes[1].step(hours, result.grid_export, where="post", color="#eb6834", label="Grid export")
    axes[1].axhline(assets.grid.import_limit_kw, color=TEXT, linestyle="--", linewidth=0.9, label="Import limit")
    axes[1].set_title("Grid exchange")
    axes[1].set_ylabel("kW")
    axes[1].legend(loc="lower right", bbox_to_anchor=(1, 1), ncol=3, fontsize=8)

    room = assets.thermal
    axes[2].axhspan(room.comfort_min_c, room.comfort_max_c, color="#2a78d6", alpha=0.08, linewidth=0)
    axes[2].plot(np.arange(97) * DT_H, result.temps, color="#eb6834", label="Room")
    axes[2].set_title("Room temperature (band = comfort range, enforced while someone is home)")
    axes[2].set_ylabel("°C")
    axes[2].set_xlabel("Hour of day")
    axes[2].set_xticks(range(0, 25, 3))
    return _save(fig, path)


def main(argv: Sequence[str] | None = None) -> int:
    cfg = load_config()
    parser = argparse.ArgumentParser(prog="python -m b2g.eval.compare_baselines")
    parser.add_argument("--start", default=cfg["evaluation"]["m5_start"])
    parser.add_argument("--days", type=int, default=cfg["evaluation"]["m5_days"])
    args = parser.parse_args(argv)
    start = date.fromisoformat(args.start)

    results = run_all(cfg, start, args.days)
    table = results_table(results)
    check = acceptance(table)
    out = REPO_ROOT / "results"
    table.round(4).to_csv(out / "m5_baselines.csv", index=False)
    (out / "m5_baselines.md").write_text(to_markdown(table, check, start, args.days), encoding="utf-8")

    assets = Assets.from_config(cfg)
    df = load_dataset(REPO_ROOT / cfg["data"]["processed_dir"])
    weekday = next(r for r in results["S5 oracle"] if r.day.weekday() not in assets.weekend_days)
    day = actual_day(df, weekday.day)
    plot_day(weekday, day.pv_kw, day.base_kw, assets, REPO_ROOT / cfg["data"]["figures_dir"] / "m5_oracle_day.png")

    print((out / "m5_baselines.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
