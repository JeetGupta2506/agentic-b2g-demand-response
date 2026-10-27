"""Build the M2 dataset: one row per 15-min slot for the configured site and period.

    python -m b2g.data.build                 # uses b2g/config/default.yaml
    python -m b2g.data.build --config my.yaml

Writes data/b2g/processed/site_15min.csv (+ _meta.json) and sanity plots to results/figures/m2_*.png.
Downloads are cached in data/b2g/raw/, so a re-run only re-computes.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np
import pandas as pd

from b2g import REPO_ROOT
from b2g.config import load_config
from b2g.data.fetch_weather import fetch_hourly, hourly_mean_to_slots, instantaneous_to_slots
from b2g.data.load_profiles import base_load_kw
from b2g.data.prices import price_series
from b2g.data.pv import pv_power_kw

# Open-Meteo variable -> (column prefix, unit suffix, hourly->15-min conversion)
VARIABLE_COLUMNS: dict[str, tuple[str, str, Callable[[pd.Series], pd.Series]]] = {
    "shortwave_radiation": ("ghi", "wm2", hourly_mean_to_slots),
    "temperature_2m": ("temp", "c", instantaneous_to_slots),
    "cloud_cover": ("cloud", "pct", instantaneous_to_slots),
}
UNITS = {
    "ghi_*_wm2": "W/m2, mean over the slot (global horizontal irradiance)",
    "temp_*_c": "degC at the slot midpoint",
    "cloud_*_pct": "% at the slot midpoint",
    "pv_*_kw": "kW, mean over the slot",
    "base_load_kw": "kW, mean over the slot",
}


def slot_index(start: date, end: date) -> pd.DatetimeIndex:
    """Slot start times from start 00:00 to end 23:45 (local time, 96 per day)."""
    return pd.date_range(f"{start} 00:00", f"{end} 23:45", freq="15min")


def weather_columns(cfg: dict[str, Any], slots: pd.DatetimeIndex, fetcher: Callable[..., pd.DataFrame]) -> dict[str, pd.Series]:
    """Actual and forecast weather on the slot grid."""
    start, end = slots[0].date(), slots[-1].date()
    raw_dir = REPO_ROOT / cfg["data"]["raw_dir"]
    columns = {}
    for source in ("actual", "forecast"):
        # One extra day: the last hour of `end` is labelled 00:00 of the next day
        hourly = fetcher(source, cfg["site"], cfg["weather"]["variables"], cfg["weather"]["forecast_lead_days"],
                         start, end + timedelta(days=1), raw_dir)
        for variable in cfg["weather"]["variables"]:
            if variable not in VARIABLE_COLUMNS:
                raise ValueError(f"no slot conversion defined for weather variable '{variable}'")
            prefix, unit, to_slots = VARIABLE_COLUMNS[variable]
            columns[f"{prefix}_{source}_{unit}"] = to_slots(hourly[variable]).reindex(slots)
    return columns


def build_dataset(cfg: dict[str, Any], fetcher: Callable[..., pd.DataFrame] = fetch_hourly) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Assemble weather (actual + day-ahead forecast), PV, base load and price per slot.
    Days with any missing value are dropped and listed in the metadata.
    """
    start = date.fromisoformat(cfg["data"]["start_date"])
    end = date.fromisoformat(cfg["data"]["end_date"])
    slots = slot_index(start, end)

    df = pd.DataFrame(weather_columns(cfg, slots, fetcher), index=slots)
    for source in ("actual", "forecast"):
        df[f"pv_{source}_kw"] = pv_power_kw(df[f"ghi_{source}_wm2"], cfg["pv"]["kwp"], cfg["pv"]["derate"])
    df["base_load_kw"] = base_load_kw(slots, cfg["base_load"], cfg["seed"])
    df["price"], price_unit = price_series(slots, cfg["tariff"])

    day_of = df.index.normalize()
    bad_days = sorted({d.date().isoformat() for d in day_of[df.isna().any(axis=1)]})
    df = df[~day_of.isin(pd.to_datetime(bad_days))]
    df.insert(0, "slot", df.index.hour * 4 + df.index.minute // 15)
    df.insert(0, "date", df.index.strftime("%Y-%m-%d"))
    df.index.name = "timestamp"

    meta = {
        "created": datetime.now().isoformat(timespec="seconds"),
        "site": cfg["site"],
        "building": cfg["building"],
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "days": int(df["date"].nunique()),
        "dropped_days": bad_days,
        "slot_minutes": cfg["data"]["slot_minutes"],
        "sources": {
            "actual": "Open-Meteo archive API (ERA5 reanalysis, best match), hourly",
            "forecast": f"Open-Meteo previous-runs API, *_previous_day{cfg['weather']['forecast_lead_days']}, hourly",
            "base_load": "synthetic (b2g/data/load_profiles.py), seeded",
            "price": cfg["tariff"]["source"],
        },
        "units": {**UNITS, "price": price_unit},
        "price_unit": price_unit,
        "pv": cfg["pv"],
        "base_load": cfg["base_load"],
        "tariff": {"source": cfg["tariff"]["source"]},
        "seed": cfg["seed"],
        "note": "All physical and economic numbers are placeholders from b2g/config/default.yaml.",
    }
    return df, meta


def save_dataset(df: pd.DataFrame, meta: dict[str, Any], processed_dir: Path) -> Path:
    """Write site_15min.csv and site_15min_meta.json; returns the CSV path."""
    processed_dir.mkdir(parents=True, exist_ok=True)
    csv_path = processed_dir / "site_15min.csv"
    df.to_csv(csv_path, float_format="%.4f")
    (processed_dir / "site_15min_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return csv_path


def load_dataset(processed_dir: Path | None = None) -> pd.DataFrame:
    """Read the processed table back (index = slot start time)."""
    processed_dir = processed_dir or REPO_ROOT / "data" / "b2g" / "processed"
    return pd.read_csv(processed_dir / "site_15min.csv", index_col="timestamp", parse_dates=["timestamp"])


def summarise(df: pd.DataFrame) -> dict[str, float]:
    """Headline numbers per day (energy in kWh or kWh/m2) and the day-ahead irradiation error."""
    daily = df.drop(columns=["date", "slot"]).resample("D").sum() * 0.25
    irr_a, irr_f = daily["ghi_actual_wm2"] / 1000, daily["ghi_forecast_wm2"] / 1000
    return {
        "irradiation_kwh_m2_day": round(float(irr_a.mean()), 2),
        "pv_actual_kwh_day": round(float(daily["pv_actual_kw"].mean()), 2),
        "base_load_kwh_day": round(float(daily["base_load_kw"].mean()), 2),
        "forecast_irradiation_mae_kwh_m2_day": round(float((irr_f - irr_a).abs().mean()), 2),
        "forecast_irradiation_nmae_pct": round(float((irr_f - irr_a).abs().mean() / irr_a.mean() * 100), 1),
        "forecast_irradiation_bias_kwh_m2_day": round(float((irr_f - irr_a).mean()), 2),
        "temp_forecast_mae_c": round(float((df["temp_forecast_c"] - df["temp_actual_c"]).abs().mean()), 2),
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Build, save, plot and print a short summary."""
    from b2g.data.plots import save_sanity_plots

    parser = argparse.ArgumentParser(prog="python -m b2g.data.build", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", help="YAML config (default b2g/config/default.yaml)")
    args = parser.parse_args(argv)
    cfg = load_config(args.config)

    print(f"Building {cfg['data']['start_date']} .. {cfg['data']['end_date']} for {cfg['site']['name']} "
          f"(downloads cached in {cfg['data']['raw_dir']})")
    df, meta = build_dataset(cfg)
    csv_path = save_dataset(df, meta, REPO_ROOT / cfg["data"]["processed_dir"])
    figures = save_sanity_plots(df, meta, REPO_ROOT / cfg["data"]["figures_dir"])

    print(f"Saved {csv_path.relative_to(REPO_ROOT)}: {len(df)} slots, {meta['days']} days, "
          f"{len(meta['dropped_days'])} dropped {meta['dropped_days'][:5]}")
    for key, value in summarise(df).items():
        print(f"  {key}: {value}")
    print("Figures: " + ", ".join(p.name for p in figures))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
