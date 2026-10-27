"""Tests for the M3 forecasters (b2g/forecasting) on a small synthetic dataset."""

import numpy as np
import pandas as pd
import pytest

from b2g.config import load_config
from b2g.data.load_profiles import base_load_kw
from b2g.forecasting import baselines, evaluate, lgbm, train
from b2g.forecasting.features import LOAD_FEATURES, PV_FEATURES, build_features, lag_days

CFG = load_config()
WEEKEND = CFG["base_load"]["weekend_days"]
SMALL_FC = {**CFG["forecasting"], "train_end": "2025-02-28", "val_end": "2025-03-15", "test_end": "2025-03-31",
            "grid": {"num_leaves": [15], "learning_rate": [0.1], "min_child_samples": [20]},
            "max_estimators": 200, "early_stopping_rounds": 20, "n_jobs": 1}


def synthetic_dataset(start="2025-01-01", end="2025-03-31", seed=0) -> pd.DataFrame:
    """M2-shaped table: clear-sky GHI x a daily cloud factor, forecast = noisy factor, seeded base load."""
    rng = np.random.default_rng(seed)
    index = pd.date_range(f"{start} 00:00", f"{end} 23:45", freq="15min")
    hour = np.asarray(index.hour + index.minute / 60 + 0.125)
    clear = np.clip(950 * np.sin(np.pi * (hour - 6.5) / 12), 0, None)
    days = index.normalize().unique()
    factor = pd.Series(rng.uniform(0.3, 1.0, len(days)), index=days)
    forecast_factor = (factor + rng.normal(0, 0.1, len(days))).clip(0.1, 1.0)
    ghi_a = clear * factor.reindex(index.normalize()).to_numpy()
    ghi_f = clear * forecast_factor.reindex(index.normalize()).to_numpy()
    df = pd.DataFrame(index=index)
    df["date"] = index.strftime("%Y-%m-%d")
    df["slot"] = index.hour * 4 + index.minute // 15
    df["ghi_actual_wm2"], df["ghi_forecast_wm2"] = ghi_a, ghi_f
    df["temp_actual_c"] = df["temp_forecast_c"] = 28.0
    df["cloud_actual_pct"] = (1 - factor.reindex(index.normalize()).to_numpy()) * 100
    df["cloud_forecast_pct"] = (1 - forecast_factor.reindex(index.normalize()).to_numpy()) * 100
    df["pv_actual_kw"], df["pv_forecast_kw"] = 4 * ghi_a / 1000, 4 * ghi_f / 1000
    df["base_load_kw"] = base_load_kw(index, CFG["base_load"], seed=42)
    df["price"] = 7.0
    return df


DF = synthetic_dataset()


# --- features -------------------------------------------------------------------------------

def test_lag_days_same_slot_and_missing_day():
    s = DF["base_load_kw"]
    lagged = lag_days(s, 1)
    assert lagged["2025-01-02 19:00"] == s["2025-01-01 19:00"]
    assert lagged["2025-01-01"].isna().all()  # no day before the data
    gap = s.drop(s["2025-01-10"].index)
    assert lag_days(gap, 1)["2025-01-11"].isna().all()  # missing day stays missing, never the wrong day


def test_features_have_all_inputs_and_96_slots_per_day():
    features = build_features(DF, WEEKEND)
    assert set(PV_FEATURES) | set(LOAD_FEATURES) <= set(features.columns)
    assert features.groupby(features.index.normalize()).size().eq(96).all()


def test_no_peeking_at_the_forecast_day():
    """Changing day d's ACTUAL values must not change day d's inputs (only later days may change)."""
    day = "2025-02-10"
    changed = DF.copy()
    for column in ("pv_actual_kw", "ghi_actual_wm2", "base_load_kw", "temp_actual_c", "cloud_actual_pct"):
        changed.loc[day, column] = changed.loc[day, column] * 3 + 1
    before, after = build_features(DF, WEEKEND), build_features(changed, WEEKEND)
    pd.testing.assert_frame_equal(before.loc[:day], after.loc[:day])
    assert not before.loc["2025-02-11"].equals(after.loc["2025-02-11"])  # next day does see it


# --- baselines and metrics ------------------------------------------------------------------

def test_baselines():
    assert baselines.persistence(DF["pv_actual_kw"])["2025-01-05 12:00"] == DF["pv_actual_kw"]["2025-01-04 12:00"]
    assert baselines.same_day_last_week(DF["base_load_kw"])["2025-01-15 20:00"] == DF["base_load_kw"]["2025-01-08 20:00"]
    pd.testing.assert_series_equal(baselines.pv_physics(DF), DF["pv_forecast_kw"])


def test_error_metrics_math():
    actual = pd.Series([1.0, 2.0, 3.0, 2.0])
    forecast = pd.Series([2.0, 2.0, 1.0, 2.0])
    m = evaluate.error_metrics(actual, forecast)
    assert m["mae_kw"] == pytest.approx(0.75)
    assert m["rmse_kw"] == pytest.approx(np.sqrt(5 / 4))
    assert m["nmae_pct"] == pytest.approx(0.75 / 2 * 100)
    assert m["bias_kw"] == pytest.approx(-0.25)


def test_split_labels_boundaries():
    labels = train.split_labels(DF.index, SMALL_FC)
    assert labels["2025-02-28 23:45"] == "train" and labels["2025-03-01 00:00"] == "val"
    assert labels["2025-03-15 23:45"] == "val" and labels["2025-03-16 00:00"] == "test"
    assert set(labels) == {"train", "val", "test"}


def test_grid_params_cover_all_combinations():
    combos = train.grid_params({"b": [1, 2], "a": [3]})
    assert combos == [{"a": 3, "b": 1}, {"a": 3, "b": 2}]


# --- LightGBM -------------------------------------------------------------------------------

def test_lgbm_is_deterministic_non_negative_and_dark_at_night():
    features = build_features(DF, WEEKEND)
    target = lgbm.TARGETS["pv"]
    params = {"num_leaves": 15, "learning_rate": 0.1, "min_child_samples": 20}
    first = lgbm.predict(target, lgbm.fit(target, features, DF["pv_actual_kw"], params, 100, 42, 1), features)
    second = lgbm.predict(target, lgbm.fit(target, features, DF["pv_actual_kw"], params, 100, 42, 1), features)
    pd.testing.assert_series_equal(first, second)
    assert (first >= 0).all()
    assert (first[features["ghi_forecast_wm2"] <= 0] == 0).all()


def test_train_and_forecast_end_to_end():
    cfg = {**CFG, "forecasting": SMALL_FC}
    forecasts, info = train.train_and_forecast(DF, cfg)
    assert set(forecasts["split"]) == {"val", "test"}
    assert forecasts.groupby("date").size().eq(96).all()
    for column in ("pv_actual", "pv_persistence", "pv_physics", "pv_lgbm",
                   "load_actual", "load_persistence", "load_weekly", "load_lgbm"):
        assert forecasts[column].notna().all(), column
    assert info["pv"]["params"] == {"learning_rate": 0.1, "min_child_samples": 20, "num_leaves": 15}
    table = evaluate.metrics_table(forecasts, SMALL_FC["monsoon_months"])
    assert set(table["model"]) == {"persistence", "physics", "weekly", "lgbm"}
    # Synthetic load = fixed shape + noise: learning the shape must beat copying yesterday's noise
    assert evaluate.lgbm_beats_persistence(table)["load"]
