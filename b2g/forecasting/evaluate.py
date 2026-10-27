"""Forecast accuracy: MAE / RMSE / nMAE / bias per model, split and season, plus two plots.

    python -m b2g.forecasting.evaluate     # re-score the saved forecasts (no training)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from b2g import REPO_ROOT
from b2g.config import load_config

# Models compared per target; forecast column = f"{target}_{model}", actual = f"{target}_actual"
MODELS = {"pv": ["persistence", "physics", "lgbm"], "load": ["persistence", "weekly", "lgbm"]}
MODEL_LABELS = {"persistence": "Persistence (yesterday)", "physics": "Weather-forecast physics",
                "weekly": "Same day last week", "lgbm": "LightGBM"}
TARGET_LABELS = {"pv": "PV power", "load": "Base load"}


def error_metrics(actual: pd.Series, forecast: pd.Series) -> dict[str, float]:
    """MAE and RMSE in kW, nMAE = MAE / mean(actual) in %, bias = mean(forecast - actual) in kW."""
    error = forecast - actual
    mae = float(error.abs().mean())
    return {
        "mae_kw": mae,
        "rmse_kw": float(np.sqrt((error ** 2).mean())),
        "nmae_pct": mae / float(actual.mean()) * 100,
        "bias_kw": float(error.mean()),
    }


def metrics_table(forecasts: pd.DataFrame, monsoon_months: list[int]) -> pd.DataFrame:
    """
    One row per (target, split, season, model). All models of a target are scored on the same slots
    (where every one of them has a value), so the comparison is fair.
    """
    monsoon = forecasts.index.month.isin(monsoon_months)
    seasons = {"all": np.ones(len(forecasts), dtype=bool), "monsoon": monsoon, "dry": ~monsoon}
    rows = []
    for target, models in MODELS.items():
        columns = [f"{target}_actual"] + [f"{target}_{m}" for m in models]
        complete = forecasts[columns].notna().all(axis=1).to_numpy()
        for split in ("val", "test"):
            for season, season_mask in seasons.items():
                mask = complete & (forecasts["split"] == split).to_numpy() & season_mask
                if not mask.any():
                    continue
                part = forecasts[mask]
                for model in models:
                    rows.append({"target": target, "split": split, "season": season, "model": model,
                                 "days": int(part.index.normalize().nunique()),
                                 **error_metrics(part[f"{target}_actual"], part[f"{target}_{model}"])})
    return pd.DataFrame(rows)


def lgbm_beats_persistence(table: pd.DataFrame) -> dict[str, bool]:
    """M3 acceptance: on the test split (all seasons), LightGBM's MAE < persistence's MAE, per target."""
    test = table[(table["split"] == "test") & (table["season"] == "all")].set_index(["target", "model"])
    return {t: bool(test.loc[(t, "lgbm"), "mae_kw"] < test.loc[(t, "persistence"), "mae_kw"]) for t in MODELS}


def to_markdown(table: pd.DataFrame) -> str:
    """Readable Markdown tables (test split first), without extra dependencies."""
    lines = ["# M3 forecast accuracy", "",
             "MAE/RMSE/bias in kW per 15-min slot; nMAE = MAE / mean actual (all slots incl. night).", ""]
    for target in MODELS:
        for split in ("test", "val"):
            part = table[(table["target"] == target) & (table["split"] == split)]
            if part.empty:
                continue
            lines += [f"## {TARGET_LABELS[target]} — {split} ({part['days'].iloc[0]} days)", "",
                      "| Season | Model | MAE kW | RMSE kW | nMAE % | Bias kW |", "|---|---|---|---|---|---|"]
            for _, r in part.iterrows():
                lines.append(f"| {r['season']} | {MODEL_LABELS[r['model']]} | {r['mae_kw']:.3f} | {r['rmse_kw']:.3f} "
                             f"| {r['nmae_pct']:.1f} | {r['bias_kw']:+.3f} |")
            lines.append("")
    return "\n".join(lines)


def save_plots(forecasts: pd.DataFrame, figures_dir: Path) -> list[Path]:
    """Example test week (PV and load) and monthly nMAE per model."""
    import matplotlib.pyplot as plt

    from b2g.data.plots import TEXT, _save, _style

    colors = {"lgbm": "#2a78d6", "persistence": "#eb6834", "physics": "#1baf7a", "weekly": "#eda100"}
    _style()
    figures_dir.mkdir(parents=True, exist_ok=True)
    saved = []

    # Week with the largest day-to-day PV change in the test set (where persistence struggles)
    test = forecasts[forecasts["split"] == "test"]
    daily_change = (test["pv_actual"] - test["pv_persistence"]).abs().groupby(test.index.normalize()).sum()
    weekly_change = daily_change.groupby(daily_change.index - pd.to_timedelta(daily_change.index.day_of_week, unit="D")).sum()
    week_start = weekly_change.idxmax()
    week = test.loc[week_start:week_start + pd.Timedelta(days=7) - pd.Timedelta(minutes=15)]

    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
    for ax, target in zip(axes, MODELS):
        ax.plot(week.index, week[f"{target}_actual"], color=TEXT, linewidth=1.8, label="Actual")
        for model in MODELS[target]:
            ax.plot(week.index, week[f"{target}_{model}"], color=colors[model], linewidth=1.2, label=MODEL_LABELS[model])
        ax.set_title(f"{TARGET_LABELS[target]}, week of {week_start:%d %b %Y}")
        ax.set_ylabel("kW")
        ax.legend(loc="lower right", bbox_to_anchor=(1, 1), ncol=2, fontsize=8)
    saved.append(_save(fig, figures_dir / "m3_test_week.png"))

    # nMAE per month (validation + test), per model
    scored = forecasts[forecasts["split"].isin(["val", "test"])]
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
    for ax, target in zip(axes, MODELS):
        month = scored.index.to_period("M").to_timestamp()
        for model in MODELS[target]:
            err = (scored[f"{target}_{model}"] - scored[f"{target}_actual"]).abs()
            nmae = err.groupby(month).mean() / scored[f"{target}_actual"].groupby(month).mean() * 100
            ax.plot(nmae.index, nmae.to_numpy(), color=colors[model], marker="o", markersize=4, label=MODEL_LABELS[model])
        ax.axvline(pd.Timestamp(test.index[0].normalize()), color=TEXT, linewidth=0.8, linestyle="--")
        ax.set_title(f"{TARGET_LABELS[target]}: monthly nMAE (validation | test)")
        ax.set_ylabel("nMAE %")
        ax.set_ylim(bottom=0)
        ax.legend(loc="lower right", bbox_to_anchor=(1, 1), ncol=3, fontsize=8)
    saved.append(_save(fig, figures_dir / "m3_error_by_month.png"))
    return saved


def load_forecasts(path: Path) -> pd.DataFrame:
    """Read the forecasts table written by train.py."""
    return pd.read_csv(path, index_col="timestamp", parse_dates=["timestamp"])


def evaluate(forecasts: pd.DataFrame, cfg: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, bool]]:
    """Score, save results/m3_forecast_metrics.{csv,md} and figures; return table and acceptance."""
    table = metrics_table(forecasts, cfg["forecasting"]["monsoon_months"])
    results_dir = REPO_ROOT / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    table.round(4).to_csv(results_dir / "m3_forecast_metrics.csv", index=False)
    (results_dir / "m3_forecast_metrics.md").write_text(to_markdown(table), encoding="utf-8")
    save_plots(forecasts, REPO_ROOT / cfg["data"]["figures_dir"])
    return table, lgbm_beats_persistence(table)


def print_summary(table: pd.DataFrame, verdict: dict[str, bool]) -> None:
    """Test-split headline per target."""
    test = table[(table["split"] == "test") & (table["season"] == "all")]
    for target in MODELS:
        print(f"\n{TARGET_LABELS[target]} — test, all seasons:")
        for _, r in test[test["target"] == target].iterrows():
            print(f"  {MODEL_LABELS[r['model']]:26} MAE {r['mae_kw']:.3f} kW  nMAE {r['nmae_pct']:5.1f} %  bias {r['bias_kw']:+.3f} kW")
    print("\nLightGBM beats persistence on test: " + ", ".join(f"{t}={v}" for t, v in verdict.items()))


def main() -> int:
    cfg = load_config()
    table, verdict = evaluate(load_forecasts(REPO_ROOT / cfg["forecasting"]["forecasts_file"]), cfg)
    print_summary(table, verdict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
