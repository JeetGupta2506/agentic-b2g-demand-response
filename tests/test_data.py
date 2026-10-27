"""Tests for the M2 data pipeline (b2g/data). No network: downloads are faked."""

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest
import requests

from b2g.config import load_config
from b2g.data import build, fetch_weather
from b2g.data.fetch_weather import hourly_mean_to_slots, instantaneous_to_slots, month_chunks
from b2g.data.load_profiles import base_load_kw
from b2g.data.prices import csv_prices, price_series, sample_prices, tou_prices
from b2g.data.pv import pv_power_kw

CFG = load_config()


def bell_ghi(index: pd.DatetimeIndex, peak: float = 900.0) -> np.ndarray:
    """Clear-sky-like hourly GHI (W/m2) labelled Open-Meteo style (label = end of the averaged hour)."""
    mid_hour = np.asarray((index - pd.Timedelta(minutes=30)).hour) + 0.5
    return np.clip(peak * np.sin(np.pi * (mid_hour - 6.5) / 12), 0, None)


def hourly_series(start: str, days: int, values=None) -> pd.Series:
    index = pd.date_range(start, periods=24 * days + 1, freq="h")
    return pd.Series(bell_ghi(index) if values is None else values, index=index)


# --- config ---------------------------------------------------------------------------------

def test_default_config_has_site_and_placeholders():
    assert (CFG["site"]["latitude"], CFG["site"]["longitude"], CFG["site"]["timezone"]) == (21.17, 72.83, "Asia/Kolkata")
    assert CFG["building"]["type"] == "house"
    assert CFG["data"]["start_date"] < CFG["data"]["end_date"]
    assert len(CFG["base_load"]["hourly_shape_weekday"]) == len(CFG["base_load"]["hourly_shape_weekend"]) == 24


# --- hourly -> 15-min -----------------------------------------------------------------------

def test_hourly_mean_to_slots_keeps_each_hours_energy():
    hourly = hourly_series("2025-05-01 00:00", 2)
    slots = hourly_mean_to_slots(hourly)
    per_hour = slots.to_numpy().reshape(-1, 4).mean(axis=1)
    np.testing.assert_allclose(per_hour, hourly.to_numpy(), atol=1e-9)
    assert (slots >= 0).all()


def test_hourly_mean_to_slots_alignment_and_night():
    hourly = hourly_series("2025-05-01 00:00", 1)
    slots = hourly_mean_to_slots(hourly)
    assert slots.index[0] == pd.Timestamp("2025-04-30 23:00")  # label 00:00 averages 23:00-00:00
    assert len(slots) == 4 * len(hourly)
    assert slots["2025-05-01 00:00":"2025-05-01 05:45"].eq(0).all()  # dark before sunrise
    assert slots["2025-05-01 12:00"] > 700


def test_hourly_mean_to_slots_marks_missing_hours():
    values = bell_ghi(pd.date_range("2025-05-01", periods=25, freq="h"))
    values[13] = np.nan  # label 13:00 = hour 12:00-13:00
    slots = hourly_mean_to_slots(hourly_series("2025-05-01 00:00", 1, values))
    assert slots["2025-05-01 12:00":"2025-05-01 12:45"].isna().all()
    assert slots.drop(slots["2025-05-01 12:00":"2025-05-01 12:45"].index).notna().all()


def test_instantaneous_to_slots_uses_slot_midpoint():
    index = pd.date_range("2025-05-01 00:00", periods=3, freq="h")
    temps = pd.Series([20.0, 24.0, 28.0], index=index)
    slots = instantaneous_to_slots(temps)
    assert len(slots) == 8 and slots.index[0] == index[0] and slots.index[-1] == pd.Timestamp("2025-05-01 01:45")
    assert slots.iloc[0] == pytest.approx(20.5)   # 00:07.5 -> 20 + 4 * 7.5/60
    assert slots.iloc[-1] == pytest.approx(27.5)  # 01:52.5


def test_instantaneous_to_slots_marks_gaps():
    index = pd.date_range("2025-05-01 00:00", periods=4, freq="h")
    slots = instantaneous_to_slots(pd.Series([20.0, np.nan, 24.0, 25.0], index=index))
    assert slots.iloc[:8].isna().all() and slots.iloc[8:].notna().all()


def test_month_chunks_cover_range_exactly():
    chunks = month_chunks(date(2024, 1, 20), date(2024, 3, 1))
    assert chunks == [(date(2024, 1, 20), date(2024, 1, 31)), (date(2024, 2, 1), date(2024, 2, 29)),
                      (date(2024, 3, 1), date(2024, 3, 1))]


# --- download cache -------------------------------------------------------------------------

class FakeOpenMeteo:
    """Stands in for requests.get: answers with 24 h of data per requested day and counts calls."""

    def __init__(self):
        self.calls = []

    def __call__(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        start, end = date.fromisoformat(params["start_date"]), date.fromisoformat(params["end_date"])
        times = pd.date_range(f"{start}", f"{end} 23:00", freq="h")
        body = {"hourly": {"time": [t.strftime("%Y-%m-%dT%H:%M") for t in times]}}
        for name in params["hourly"].split(","):
            body["hourly"][name] = [1.0] * len(times)
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(body).encode()
        return response


def test_fetch_uses_raw_cache_and_maps_forecast_names(tmp_path):
    fake = FakeOpenMeteo()
    args = ("forecast", CFG["site"], ["shortwave_radiation", "temperature_2m"], 1, date(2025, 1, 30), date(2025, 2, 2), tmp_path)
    first = fetch_weather.fetch_hourly(*args, get=fake)
    assert len(fake.calls) == 2  # January and February chunks
    assert fake.calls[0][1]["hourly"] == "shortwave_radiation_previous_day1,temperature_2m_previous_day1"
    assert list(first.columns) == ["shortwave_radiation", "temperature_2m"] and len(first) == 4 * 24
    second = fetch_weather.fetch_hourly(*args, get=fake)
    assert len(fake.calls) == 2  # served from data/b2g/raw cache
    pd.testing.assert_frame_equal(first, second)


def test_fetch_rejects_incomplete_response(tmp_path):
    def short_answer(url, params=None, timeout=None):
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps({"hourly": {"time": ["2025-01-01T00:00"], "temperature_2m": [1.0]}}).encode()
        return response
    with pytest.raises(ValueError):
        fetch_weather.fetch_chunk("actual", CFG["site"], ["temperature_2m"], 1, date(2025, 1, 1), date(2025, 1, 1), tmp_path, get=short_answer)
    assert not list(tmp_path.iterdir())  # nothing cached


# --- PV, base load, prices ------------------------------------------------------------------

def test_pv_formula():
    ghi = pd.Series([0.0, 500.0, 1000.0, -5.0])
    np.testing.assert_allclose(pv_power_kw(ghi, kwp=5.0, derate=0.8), [0.0, 2.0, 4.0, 0.0])


def test_base_load_seeded_per_day_and_range_independent():
    slots = build.slot_index(date(2025, 5, 1), date(2025, 5, 7))
    a = base_load_kw(slots, CFG["base_load"], seed=42)
    b = base_load_kw(build.slot_index(date(2025, 5, 5), date(2025, 5, 7)), CFG["base_load"], seed=42)
    pd.testing.assert_series_equal(a["2025-05-05":], b)
    assert not a.equals(base_load_kw(slots, CFG["base_load"], seed=7))
    assert (a > 0).all()


def test_base_load_daily_energy_and_weekend_shape():
    slots = build.slot_index(date(2025, 1, 1), date(2025, 12, 31))
    load = base_load_kw(slots, CFG["base_load"], seed=42)
    daily_kwh = load.resample("D").sum() * 0.25
    weekend = daily_kwh.index.day_of_week.isin(CFG["base_load"]["weekend_days"])
    assert daily_kwh[~weekend].mean() == pytest.approx(CFG["base_load"]["daily_kwh_weekday"], rel=0.02)
    assert daily_kwh[weekend].mean() == pytest.approx(CFG["base_load"]["daily_kwh_weekend"], rel=0.02)
    evening = load[load.index.hour == 19].mean()
    assert evening > load[load.index.hour == 3].mean() * 3  # evening peak, quiet night


def test_tou_prices_follow_periods():
    slots = build.slot_index(date(2025, 5, 1), date(2025, 5, 1))
    prices = tou_prices(slots, CFG["tariff"]["tou"]["periods"])
    assert len(prices) == 96
    assert prices["2025-05-01 12:00"] == 5.6 and prices["2025-05-01 19:00"] == 8.4 and prices["2025-05-01 03:00"] == 7.0
    assert prices["2025-05-01 08:45"] == 7.0 and prices["2025-05-01 09:00"] == 5.6  # boundary


def test_tou_prices_reject_gaps_and_misaligned_periods():
    slots = build.slot_index(date(2025, 5, 1), date(2025, 5, 1))
    with pytest.raises(ValueError):
        tou_prices(slots, [{"start": "00:00", "end": "12:00", "price": 1}, {"start": "13:00", "end": "24:00", "price": 2}])
    with pytest.raises(ValueError):
        tou_prices(slots, [{"start": "00:00", "end": "12:10", "price": 1}, {"start": "12:10", "end": "24:00", "price": 2}])


def test_sample_prices_are_original_repo_prices_in_per_kwh():
    slots = build.slot_index(date(2025, 5, 1), date(2025, 5, 2))
    prices = sample_prices(slots, CFG["tariff"]["sample"]["path"])
    original = json.loads((build.REPO_ROOT / "data" / "prices_sample.json").read_text())["prices"]
    np.testing.assert_allclose(prices.to_numpy()[:96], np.asarray(original) / 1000)
    np.testing.assert_allclose(prices.to_numpy()[96:], prices.to_numpy()[:96])


def test_csv_prices_align_and_require_every_slot(tmp_path, monkeypatch):
    monkeypatch.setattr("b2g.data.prices.REPO_ROOT", tmp_path)
    slots = build.slot_index(date(2025, 5, 1), date(2025, 5, 1))
    pd.DataFrame({"timestamp": slots, "price": np.arange(96) * 100.0}).to_csv(tmp_path / "iex.csv", index=False)
    cfg = {**CFG["tariff"]["csv"], "path": "iex.csv"}
    prices = csv_prices(slots, cfg)
    assert prices.iloc[10] == pytest.approx(1.0)  # 1000 Rs/MWh -> 1 Rs/kWh
    pd.DataFrame({"timestamp": slots[:-1], "price": 1.0}).to_csv(tmp_path / "iex.csv", index=False)
    with pytest.raises(ValueError):
        csv_prices(slots, cfg)


def test_price_series_reports_unit():
    slots = build.slot_index(date(2025, 5, 1), date(2025, 5, 1))
    assert price_series(slots, CFG["tariff"])[1] == "INR/kWh"
    assert price_series(slots, {**CFG["tariff"], "source": "sample"})[1] == "EUR/kWh"


# --- full build on fake weather -------------------------------------------------------------

def fake_fetcher(missing_forecast_day: str | None = None):
    """Weather 'download' with a clear-sky GHI, warm temperatures and no clouds."""
    def fetch(source, site, variables, lead_days, start, end, raw_dir):
        index = pd.date_range(f"{start} 00:00", f"{end} 23:00", freq="h")
        frame = pd.DataFrame({"shortwave_radiation": bell_ghi(index) * (0.9 if source == "forecast" else 1.0),
                              "temperature_2m": 30.0, "cloud_cover": 0.0}, index=index)
        if source == "forecast" and missing_forecast_day:  # a midday gap, so neighbouring days stay complete
            frame.loc[f"{missing_forecast_day} 10:00":f"{missing_forecast_day} 14:00", "temperature_2m"] = np.nan
        return frame
    return fetch


def small_config(start="2025-05-01", end="2025-05-03"):
    return {**CFG, "data": {**CFG["data"], "start_date": start, "end_date": end}}


def test_build_dataset_shape_columns_and_units():
    df, meta = build.build_dataset(small_config(), fetcher=fake_fetcher())
    assert len(df) == 3 * 96 and meta["days"] == 3 and meta["dropped_days"] == []
    assert df.groupby("date").size().eq(96).all()
    assert list(df["slot"][:3]) == [0, 1, 2] and df["slot"].max() == 95
    for column in ("ghi_actual_wm2", "ghi_forecast_wm2", "temp_actual_c", "temp_forecast_c", "cloud_actual_pct",
                   "cloud_forecast_pct", "pv_actual_kw", "pv_forecast_kw", "base_load_kw", "price"):
        assert column in df.columns and df[column].notna().all()
    assert df["pv_actual_kw"].max() <= CFG["pv"]["kwp"]
    assert (df["pv_forecast_kw"] <= df["pv_actual_kw"] + 1e-9).all()  # fake forecast is 10 % lower
    assert meta["price_unit"] == "INR/kWh"


def test_build_dataset_drops_days_with_missing_data():
    df, meta = build.build_dataset(small_config(), fetcher=fake_fetcher(missing_forecast_day="2025-05-02"))
    assert meta["dropped_days"] == ["2025-05-02"] and meta["days"] == 2
    assert "2025-05-02" not in set(df["date"])


def test_save_and_load_round_trip(tmp_path):
    df, meta = build.build_dataset(small_config(), fetcher=fake_fetcher())
    build.save_dataset(df, meta, tmp_path)
    back = build.load_dataset(tmp_path)
    assert len(back) == len(df) and back.index[0] == df.index[0]
    np.testing.assert_allclose(back["pv_actual_kw"], df["pv_actual_kw"], atol=1e-4)
    assert json.loads((tmp_path / "site_15min_meta.json").read_text())["days"] == 3
