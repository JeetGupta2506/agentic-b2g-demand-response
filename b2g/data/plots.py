"""Sanity plots for the M2 dataset (static PNGs in results/figures/)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # no window; files only
import matplotlib.pyplot as plt
import pandas as pd

# Reference palette (dataviz skill): light surface, text inks, categorical slots 1-2 in fixed order
SURFACE, TEXT, TEXT_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
ACTUAL, FORECAST = "#2a78d6", "#eb6834"  # slot 1 blue, slot 2 orange
SLOT_H = 0.25  # hours per 15-min slot


def _style() -> None:
    """Recessive axes and grid, thin lines."""
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID, "axes.labelcolor": TEXT_2, "axes.titlecolor": TEXT,
        "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
        "xtick.color": TEXT_2, "ytick.color": TEXT_2, "text.color": TEXT,
        "lines.linewidth": 1.5, "legend.frameon": False, "font.size": 10,
    })


def _save(fig: plt.Figure, path: Path) -> Path:
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def _two_lines(ax: plt.Axes, actual: pd.Series, forecast: pd.Series, ylabel: str, title: str) -> None:
    ax.plot(actual.index, actual.to_numpy(), color=ACTUAL, label="Actual (ERA5 reanalysis)")
    ax.plot(forecast.index, forecast.to_numpy(), color=FORECAST, label="Day-ahead forecast", alpha=0.9)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.legend(loc="lower right", bbox_to_anchor=(1, 1), ncol=2)  # above the plot, right of the title


def save_sanity_plots(df: pd.DataFrame, meta: dict[str, Any], out_dir: Path) -> list[Path]:
    """One figure per series plus a forecast-vs-actual check; returns the saved paths."""
    _style()
    out_dir.mkdir(parents=True, exist_ok=True)
    site = meta["site"]["name"]
    daily = df.resample("D")
    saved = []

    # Solar irradiation per day (kWh/m2): sum of 15-min GHI (W/m2) x 0.25 h / 1000
    irr_a = daily["ghi_actual_wm2"].sum() * SLOT_H / 1000
    irr_f = daily["ghi_forecast_wm2"].sum() * SLOT_H / 1000
    fig, ax = plt.subplots(figsize=(11, 4))
    _two_lines(ax, irr_a, irr_f, "kWh/m² per day", f"Daily solar irradiation, {site}")
    saved.append(_save(fig, out_dir / "m2_solar_daily.png"))

    # One example week at 15-min resolution (first full Monday-Sunday in May of the last year)
    year = df.index[-1].year
    may = df.loc[f"{year}-05-01":f"{year}-05-31"]
    week_start = may.index[may.index.day_of_week == 0][0].normalize() if len(may) else df.index[0].normalize()
    week = df.loc[week_start:week_start + pd.Timedelta(days=7) - pd.Timedelta(minutes=15)]
    fig, ax = plt.subplots(figsize=(11, 4))
    _two_lines(ax, week["ghi_actual_wm2"], week["ghi_forecast_wm2"], "W/m²",
               f"Solar irradiance (GHI), 15-min slots, week of {week_start:%d %b %Y}")
    saved.append(_save(fig, out_dir / "m2_solar_week.png"))

    fig, ax = plt.subplots(figsize=(11, 4))
    _two_lines(ax, daily["temp_actual_c"].mean(), daily["temp_forecast_c"].mean(), "°C",
               f"Daily mean air temperature, {site}")
    saved.append(_save(fig, out_dir / "m2_temperature.png"))

    fig, ax = plt.subplots(figsize=(11, 4))
    _two_lines(ax, daily["cloud_actual_pct"].mean(), daily["cloud_forecast_pct"].mean(), "%",
               f"Daily mean cloud cover, {site}")
    saved.append(_save(fig, out_dir / "m2_cloud.png"))

    # PV energy per month (kWh), actual weather
    monthly_pv = df["pv_actual_kw"].resample("MS").sum() * SLOT_H
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.bar(monthly_pv.index, monthly_pv.to_numpy(), width=24, color=ACTUAL)
    ax.set_title(f"PV energy per month, {meta['pv']['kwp']} kWp array (placeholder size)")
    ax.set_ylabel("kWh per month")
    ax.grid(axis="x", visible=False)
    saved.append(_save(fig, out_dir / "m2_pv_monthly.png"))

    # Average base-load profile over the day, weekday vs weekend
    weekend = df.index.day_of_week.isin(meta["base_load"]["weekend_days"])
    slot_hours = df["slot"] / 4
    fig, ax = plt.subplots(figsize=(9, 4))
    for mask, color, label in ((~weekend, ACTUAL, "Weekday"), (weekend, FORECAST, "Weekend")):
        profile = df.loc[mask, "base_load_kw"].groupby(slot_hours[mask]).mean()
        ax.plot(profile.index, profile.to_numpy(), color=color, label=label)
    ax.set_title("Average household base load over the day (synthetic, excludes AC/EV/battery)")
    ax.set_xlabel("Hour of day")
    ax.set_ylabel("kW")
    ax.set_xticks(range(0, 25, 3))
    ax.legend(loc="upper left")
    saved.append(_save(fig, out_dir / "m2_base_load.png"))

    # Tariff over one day
    first_day = df.loc[df.index[0].normalize():df.index[0].normalize() + pd.Timedelta(hours=23, minutes=45)]
    fig, ax = plt.subplots(figsize=(9, 3.5))
    ax.step(first_day["slot"] / 4, first_day["price"].to_numpy(), where="post", color=ACTUAL)
    ax.set_title(f"Electricity price over the day ({meta['tariff']['source']} tariff, placeholder values)")
    ax.set_xlabel("Hour of day")
    ax.set_ylabel(meta["price_unit"])
    ax.set_xticks(range(0, 25, 3))
    ax.set_ylim(bottom=0)
    saved.append(_save(fig, out_dir / "m2_price.png"))

    # Forecast check: daily irradiation, forecast vs actual
    fig, ax = plt.subplots(figsize=(5.5, 5.5))
    ax.scatter(irr_a.to_numpy(), irr_f.to_numpy(), s=14, color=ACTUAL, alpha=0.55, linewidths=0)
    top = float(max(irr_a.max(), irr_f.max())) * 1.05
    ax.plot([0, top], [0, top], color=TEXT_2, linewidth=1, linestyle="--", label="Perfect forecast")
    ax.set_xlim(0, top)
    ax.set_ylim(0, top)
    ax.set_aspect("equal")
    ax.set_title("Day-ahead forecast vs actual\n(daily irradiation)")
    ax.set_xlabel("Actual, kWh/m² per day")
    ax.set_ylabel("Forecast, kWh/m² per day")
    ax.legend(loc="upper left")
    saved.append(_save(fig, out_dir / "m2_forecast_check.png"))
    return saved
