"""Download hourly weather from Open-Meteo (actual + day-ahead forecast) and convert it to 15-min slots.

Sources (no API key needed):
- "actual":   archive API (ERA5 reanalysis), what the weather really was.
- "forecast": previous-runs API, variable `<name>_previous_day<lead>` = the forecast issued
              <lead> days earlier, i.e. what a day-ahead planner would have known.

Each request covers at most one calendar month and is cached as raw JSON in data/b2g/raw/, so a
re-run never downloads the same chunk twice. All times are local site time (Asia/Kolkata, no DST).
"""

from __future__ import annotations

import json
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
import requests

SOURCES = {
    "actual": "https://archive-api.open-meteo.com/v1/archive",
    "forecast": "https://previous-runs-api.open-meteo.com/v1/forecast",
}
SLOT = pd.Timedelta(minutes=15)
HOUR = pd.Timedelta(hours=1)


def month_chunks(start: date, end: date) -> list[tuple[date, date]]:
    """Split [start, end] (inclusive) into calendar-month pieces."""
    chunks = []
    current = start
    while current <= end:
        next_month = (current.replace(day=1) + timedelta(days=32)).replace(day=1)
        chunk_end = min(end, next_month - timedelta(days=1))
        chunks.append((current, chunk_end))
        current = chunk_end + timedelta(days=1)
    return chunks


def _request_params(source: str, site: dict[str, Any], variables: list[str], lead_days: int,
                    start: date, end: date) -> dict[str, Any]:
    """Query parameters for one Open-Meteo request."""
    names = variables if source == "actual" else [f"{v}_previous_day{lead_days}" for v in variables]
    return {
        "latitude": site["latitude"],
        "longitude": site["longitude"],
        "timezone": site["timezone"],
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "hourly": ",".join(names),
    }


def fetch_chunk(source: str, site: dict[str, Any], variables: list[str], lead_days: int,
                start: date, end: date, raw_dir: Path,
                get: Callable[..., requests.Response] = requests.get, retries: int = 3) -> dict[str, Any]:
    """
    Hourly data for [start, end] from `source` ("actual" | "forecast"), from the raw cache if present.
    Returns the API's "hourly" block with forecast names mapped back to the plain variable names.
    """
    raw_dir = Path(raw_dir)
    cache_file = raw_dir / f"{source}_{start.isoformat()}_{end.isoformat()}.json"
    if cache_file.exists():
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
    else:
        params = _request_params(source, site, variables, lead_days, start, end)
        for attempt in range(retries + 1):
            try:
                response = get(SOURCES[source], params=params, timeout=120)
                if response.status_code == 429 or response.status_code >= 500:
                    raise requests.exceptions.HTTPError(f"HTTP {response.status_code}", response=response)
                response.raise_for_status()
                break
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
                status = getattr(getattr(e, "response", None), "status_code", None)
                if attempt == retries or (status is not None and status < 500 and status != 429):
                    raise
                time.sleep(5 * 2 ** attempt)
        payload = response.json()
        expected_hours = 24 * ((end - start).days + 1)
        if len(payload.get("hourly", {}).get("time", [])) != expected_hours:
            raise ValueError(f"{source} {start}..{end}: expected {expected_hours} hours, got "
                             f"{len(payload.get('hourly', {}).get('time', []))}")
        raw_dir.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(payload), encoding="utf-8")

    hourly = payload["hourly"]
    suffix = f"_previous_day{lead_days}"
    return {k.removesuffix(suffix): v for k, v in hourly.items()}


def fetch_hourly(source: str, site: dict[str, Any], variables: list[str], lead_days: int,
                 start: date, end: date, raw_dir: Path, **kwargs: Any) -> pd.DataFrame:
    """Hourly DataFrame for [start, end], indexed by Open-Meteo's local label time, one column per variable."""
    frames = []
    for chunk_start, chunk_end in month_chunks(start, end):
        hourly = fetch_chunk(source, site, variables, lead_days, chunk_start, chunk_end, raw_dir, **kwargs)
        frame = pd.DataFrame({v: hourly[v] for v in variables}, index=pd.to_datetime(hourly["time"]), dtype=float)
        frames.append(frame)
    return pd.concat(frames).sort_index()


def _minutes(index: pd.DatetimeIndex) -> np.ndarray:
    """Timestamps as float minutes (for numpy interpolation); unit pinned because pandas 3 indexes may be s/us/ns."""
    return index.as_unit("ns").asi8.astype(np.float64) / 60e9


def _check_hourly(series: pd.Series) -> None:
    """Interpolation assumes a gap-free hourly index."""
    if len(series) < 2 or (pd.Series(series.index).diff().dropna() != HOUR).any():
        raise ValueError("expected a continuous hourly series")


def hourly_mean_to_slots(series: pd.Series) -> pd.Series:
    """
    Hourly means -> 15-min slot means (W/m2 stays W/m2), keeping each hour's energy exactly.

    Open-Meteo labels radiation with the END of the hour it averages (label 10:00 = mean 09:00-10:00).
    The hourly means are placed at hour midpoints, linearly interpolated to slot midpoints, clipped at 0,
    then rescaled so the 4 slots of every hour average to that hour's value (a flat step if the
    interpolation gives 0). Hours with a missing value give missing slots.
    Output index = slot start time.
    """
    _check_hourly(series)
    hour_start = series.index - HOUR
    hour_values = series.to_numpy(dtype=float)
    slots = pd.date_range(hour_start[0], hour_start[-1] + 3 * SLOT, freq=SLOT)

    known = ~np.isnan(hour_values)
    hour_mid = _minutes(hour_start) + 30
    slot_mid = _minutes(slots) + 7.5
    smooth = np.interp(slot_mid, hour_mid[known], hour_values[known]).clip(min=0).reshape(-1, 4)

    target = np.where(known, hour_values, np.nan).clip(min=0)[:, None]
    slot_mean = smooth.mean(axis=1, keepdims=True)
    scaled = np.where(slot_mean > 0, smooth * target / np.where(slot_mean > 0, slot_mean, 1), target)
    return pd.Series(scaled.reshape(-1), index=slots, name=series.name)


def instantaneous_to_slots(series: pd.Series) -> pd.Series:
    """
    Hourly instantaneous values (e.g. temperature at 10:00) -> value at each 15-min slot's midpoint,
    by linear interpolation. A slot is missing if either neighbouring hourly value is missing.
    Output covers the slots from the first to the last label hour (index = slot start time).
    """
    _check_hourly(series)
    values = series.to_numpy(dtype=float)
    known = ~np.isnan(values)
    slots = pd.date_range(series.index[0], series.index[-1] - SLOT, freq=SLOT)
    label_min, slot_mid = _minutes(series.index), _minutes(slots) + 7.5
    out = np.interp(slot_mid, label_min[known], values[known])
    touches_gap = np.interp(slot_mid, label_min, (~known).astype(float)) > 0
    out[touches_gap] = np.nan
    return pd.Series(out, index=slots, name=series.name)
