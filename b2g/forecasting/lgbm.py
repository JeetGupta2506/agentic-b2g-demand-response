"""LightGBM day-ahead models for PV and base load (one row per 15-min slot)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd

from b2g.forecasting.features import LOAD_FEATURES, PV_FEATURES


@dataclass(frozen=True)
class Target:
    """What one model predicts: target column (kW), its inputs, and physical post-processing."""

    name: str
    column: str
    features: list[str]
    dark_column: str | None = None  # predict exactly 0 where this forecast column is 0 (no sun)


TARGETS = {
    "pv": Target("pv", "pv_actual_kw", PV_FEATURES, dark_column="ghi_forecast_wm2"),
    "load": Target("load", "base_load_kw", LOAD_FEATURES),
}


def booster_params(params: dict[str, Any], seed: int, n_jobs: int) -> dict[str, Any]:
    """Deterministic LightGBM settings (same seed + same thread count -> identical model)."""
    return {"objective": "regression", "metric": "l1", "seed": seed, "num_threads": n_jobs,
            "deterministic": True, "force_row_wise": True, "verbose": -1, **params}


def fit(target: Target, features: pd.DataFrame, actual: pd.Series, params: dict[str, Any], n_estimators: int,
        seed: int, n_jobs: int, valid: tuple[pd.DataFrame, pd.Series] | None = None,
        early_stopping_rounds: int | None = None) -> lgb.Booster:
    """
    Train on rows with a known target (native LightGBM API, no scikit-learn needed).
    With `valid`, stops early on validation MAE; `booster.best_iteration` then holds the best tree count.
    """
    known = actual.notna()
    train_set = lgb.Dataset(features.loc[known, target.features], actual[known], free_raw_data=False)
    valid_sets, callbacks = [], []
    if valid is not None:
        valid_x, valid_y = valid
        valid_known = valid_y.notna()
        valid_sets = [lgb.Dataset(valid_x.loc[valid_known, target.features], valid_y[valid_known], reference=train_set)]
        if early_stopping_rounds:
            callbacks = [lgb.early_stopping(early_stopping_rounds, verbose=False)]
    return lgb.train(booster_params(params, seed, n_jobs), train_set, num_boost_round=n_estimators,
                     valid_sets=valid_sets, callbacks=callbacks)


def predict(target: Target, model: lgb.Booster, features: pd.DataFrame) -> pd.Series:
    """Forecast in kW: never negative, and 0 in slots where no sun is forecast (PV)."""
    values = np.clip(model.predict(features[target.features], num_iteration=model.best_iteration or None), 0, None)
    if target.dark_column is not None:
        values = np.where(features[target.dark_column].to_numpy() <= 0, 0.0, values)
    return pd.Series(values, index=features.index, name=f"{target.name}_lgbm")
