"""Train the M3 forecasters and write day-ahead forecasts for the validation and test days.

    python -m b2g.forecasting.train

Validation forecasts come from models trained on the train split only; test forecasts from models
retrained on train + validation with the settings chosen on validation. Writes
data/b2g/processed/forecasts.csv, results/m3_lgbm_info.json, the metrics and the m3_* figures.
"""

from __future__ import annotations

import itertools
import json
from typing import Any

import pandas as pd

from b2g import REPO_ROOT
from b2g.config import load_config
from b2g.data.build import load_dataset
from b2g.forecasting import baselines, evaluate, lgbm
from b2g.forecasting.features import build_features


def split_labels(index: pd.DatetimeIndex, fc: dict[str, Any]) -> pd.Series:
    """'train' / 'val' / 'test' per slot from the inclusive end dates; '' after test_end."""
    day = index.normalize()
    labels = pd.Series("", index=index)
    labels[day <= pd.Timestamp(fc["test_end"])] = "test"
    labels[day <= pd.Timestamp(fc["val_end"])] = "val"
    labels[day <= pd.Timestamp(fc["train_end"])] = "train"
    return labels


def grid_params(grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
    """All combinations of the grid, in a fixed order."""
    keys = sorted(grid)
    return [dict(zip(keys, values)) for values in itertools.product(*(grid[k] for k in keys))]


def tune(target: lgbm.Target, features: pd.DataFrame, actual: pd.Series, split: pd.Series,
         fc: dict[str, Any], seed: int) -> tuple[dict[str, Any], int, list[dict[str, Any]]]:
    """Fit each grid point on train with early stopping on val; return best params, iterations, all trials."""
    train, val = split == "train", split == "val"
    trials = []
    for params in grid_params(fc["grid"]):
        model = lgbm.fit(target, features[train], actual[train], params, fc["max_estimators"], seed, fc["n_jobs"],
                         valid=(features[val], actual[val]), early_stopping_rounds=fc["early_stopping_rounds"])
        val_mae = float((lgbm.predict(target, model, features[val]) - actual[val]).abs().mean())
        trials.append({"params": params, "n_estimators": int(model.best_iteration or fc["max_estimators"]),
                       "val_mae_kw": val_mae})
    best = min(trials, key=lambda t: t["val_mae_kw"])
    return best["params"], best["n_estimators"], trials


def train_and_forecast(df: pd.DataFrame, cfg: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """All baseline and LightGBM forecasts (kW) for validation and test slots, plus model info."""
    fc, seed = cfg["forecasting"], cfg["seed"]
    features = build_features(df, cfg["base_load"]["weekend_days"])
    split = split_labels(df.index, fc)
    scored = split.isin(["val", "test"])

    out = pd.DataFrame({"date": df["date"], "slot": df["slot"], "split": split}, index=df.index)
    out["pv_actual"] = df["pv_actual_kw"]
    out["pv_persistence"] = baselines.persistence(df["pv_actual_kw"])
    out["pv_physics"] = baselines.pv_physics(df)
    out["load_actual"] = df["base_load_kw"]
    out["load_persistence"] = baselines.persistence(df["base_load_kw"])
    out["load_weekly"] = baselines.same_day_last_week(df["base_load_kw"])

    info: dict[str, Any] = {"seed": seed, "splits": {k: fc[k] for k in ("train_end", "val_end", "test_end")}}
    for name, target in lgbm.TARGETS.items():
        actual = df[target.column]
        params, n_estimators, trials = tune(target, features, actual, split, fc, seed)
        print(f"  {name}: best {params}, {n_estimators} trees, val MAE {min(t['val_mae_kw'] for t in trials):.4f} kW")
        out[f"{name}_lgbm"] = float("nan")
        for fit_on, predict_on in ((["train"], "val"), (["train", "val"], "test")):
            rows = split.isin(fit_on)
            model = lgbm.fit(target, features[rows], actual[rows], params, n_estimators, seed, fc["n_jobs"])
            target_rows = split == predict_on
            out.loc[target_rows, f"{name}_lgbm"] = lgbm.predict(target, model, features[target_rows]).to_numpy()
        gain = pd.Series(model.feature_importance("gain"), index=target.features)
        info[name] = {"params": params, "n_estimators": n_estimators, "trials": trials,
                      "feature_importance_gain_pct": (gain / gain.sum() * 100).round(1).sort_values(ascending=False).to_dict()}
    return out[scored], info


def main() -> int:
    cfg = load_config()
    df = load_dataset(REPO_ROOT / cfg["data"]["processed_dir"])
    print(f"Training on {df['date'].nunique()} days (train <= {cfg['forecasting']['train_end']}, "
          f"val <= {cfg['forecasting']['val_end']}, test <= {cfg['forecasting']['test_end']})")
    forecasts, info = train_and_forecast(df, cfg)

    path = REPO_ROOT / cfg["forecasting"]["forecasts_file"]
    path.parent.mkdir(parents=True, exist_ok=True)
    forecasts.to_csv(path, float_format="%.4f")
    (REPO_ROOT / "results").mkdir(exist_ok=True)
    (REPO_ROOT / "results" / "m3_lgbm_info.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    print(f"Saved {path.relative_to(REPO_ROOT)} ({forecasts['date'].nunique()} days)")

    table, verdict = evaluate.evaluate(forecasts, cfg)
    evaluate.print_summary(table, verdict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
