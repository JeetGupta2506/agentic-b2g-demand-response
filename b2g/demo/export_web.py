"""Export everything the demo shows as static JSON for a web frontend (e.g. Next.js `public/data/`).

    python -m b2g.demo.export_web [--out web/public/data]

Files: site.json (house, headline numbers, daily profiles, daily solar), examples.json (the pre-run
requests from results/demo/), results.json (forecast accuracy and the one-week comparison).
Units: kW for power, kWh for energy, °C, INR; 96 points = 15-min slots of one day.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from b2g import REPO_ROOT
from b2g.config import load_config
from b2g.data.build import load_dataset
from b2g.demo.core import EXAMPLES, load_examples

MODEL_NAMES = {"persistence": "Same as yesterday", "physics": "Weather-forecast physics",
               "weekly": "Same day last week", "lgbm": "LightGBM (ML)"}


def _r(values, nd: int = 3) -> list[float]:
    return [round(float(v), nd) for v in values]


def site_json(cfg: dict[str, Any]) -> dict[str, Any]:
    """House specs, headline numbers, the average day (96 slots) and daily solar (actual vs forecast)."""
    df = load_dataset()
    daily = df.drop(columns=["date", "slot"]).resample("D").sum() * 0.25          # kW x 0.25 h -> kWh
    irr_a, irr_f = daily["ghi_actual_wm2"] / 1000, daily["ghi_forecast_wm2"] / 1000
    by_slot = df.groupby("slot")[["pv_actual_kw", "base_load_kw", "price"]].mean()
    return {
        "house": {"city": cfg["site"]["name"], "pv_kwp": cfg["pv"]["kwp"], "battery_kwh": cfg["battery"]["capacity_kwh"],
                  "ev_kwh": cfg["ev"]["capacity_kwh"], "ev_charger_kw": cfg["ev"]["p_max_kw"],
                  "ac_kw": cfg["thermal"]["p_cool_max_kw"], "grid_limit_kw": cfg["grid"]["import_limit_kw"],
                  "comfort_c": [cfg["thermal"]["comfort_min_c"], cfg["thermal"]["comfort_max_c"]],
                  "weekday_away": [cfg["ev"]["departure"], cfg["ev"]["arrival"]],
                  "data_range": [cfg["data"]["start_date"], cfg["data"]["end_date"]]},
        "headline": {"solar_kwh_per_day": round(float(daily["pv_actual_kw"].mean()), 2),
                     "base_demand_kwh_per_day": round(float(daily["base_load_kw"].mean()), 2),
                     "forecast_error_pct": round(float((irr_f - irr_a).abs().mean() / irr_a.mean() * 100), 1),
                     "days_of_data": int(df["date"].nunique())},
        "average_day": {"solar_kw": _r(by_slot["pv_actual_kw"]), "demand_kw": _r(by_slot["base_load_kw"]),
                        "price_inr_per_kwh": _r(by_slot["price"], 2)},
        "daily_solar": {"date": [d.strftime("%Y-%m-%d") for d in daily.index],
                        "actual_kwh": _r(daily["pv_actual_kw"], 2), "forecast_kwh": _r(daily["pv_forecast_kw"], 2)},
    }


def results_json(cfg: dict[str, Any]) -> dict[str, Any]:
    """Forecast accuracy on the test period (overall and by month) and the one-week system comparison."""
    m3 = pd.read_csv(REPO_ROOT / "results" / "m3_forecast_metrics.csv")
    test = m3[(m3["split"] == "test") & (m3["season"] == "all")]
    accuracy = [{"target": "Solar" if r.target == "pv" else "House demand", "model": MODEL_NAMES[r.model],
                 "nmae_pct": round(float(r.nmae_pct), 1)} for r in test.itertuples()]

    fc = pd.read_csv(REPO_ROOT / cfg["forecasting"]["forecasts_file"], parse_dates=["timestamp"])
    fc["month"] = fc["timestamp"].dt.strftime("%Y-%m")
    monthly: dict[str, Any] = {"month": sorted(fc["month"].unique())}
    for target, models in (("pv", ("persistence", "physics", "lgbm")), ("load", ("persistence", "weekly", "lgbm"))):
        g = fc.groupby("month")
        monthly[target] = {MODEL_NAMES[m]: _r((g.apply(lambda x: (x[f"{target}_{m}"] - x[f"{target}_actual"]).abs().mean()
                                                        / x[f"{target}_actual"].mean() * 100, include_groups=False)), 1)
                           for m in models}

    m5 = pd.read_csv(REPO_ROOT / "results" / "m5_baselines.csv")
    week = m5.groupby("system", sort=False).agg(total_inr=("total_cost", "mean"), electricity_inr=("electricity_cost", "mean"),
                                                discomfort_degc_h=("comfort_dh", "mean"), peak_kw=("peak_import_kw", "mean"),
                                                solar_used_pct=("self_consumption_pct", "mean")).round(2).reset_index()
    return {"forecast_accuracy_test": accuracy, "forecast_error_by_month": monthly,
            "validation_test_split": {"train_end": cfg["forecasting"]["train_end"], "val_end": cfg["forecasting"]["val_end"],
                                      "test_end": cfg["forecasting"]["test_end"]},
            "week_comparison": {"dates": [m5["date"].min(), m5["date"].max()], "rows": week.to_dict("records")}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(REPO_ROOT / "results" / "web_data"))
    out = Path(parser.parse_args().out)
    out.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    files = {"site.json": site_json(cfg), "examples.json": [d for d in load_examples() if d["title"] in {t for t, _, _ in EXAMPLES}], "results.json": results_json(cfg)}
    for name, data in files.items():
        (out / name).write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"{out / name}  {(out / name).stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
