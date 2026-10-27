"""Sanity figure for the thermal model on the hottest day in the M2 data.

    python -m b2g.models.demo     -> results/figures/m4_thermal_demo.png

Compares the room with the AC off and with a simple thermostat (AC at full power whenever someone is
home and the room is above the comfort maximum). The thermostat is only an illustration of the
physics, not the S1 rule-based baseline (that is M5).
"""

from __future__ import annotations

import numpy as np

from b2g import REPO_ROOT
from b2g.config import load_config
from b2g.data.build import load_dataset
from b2g.models import DT_H, SLOTS, thermal


def thermostat(params: thermal.ThermalParams, t_out, gains, occupied, t0: float) -> tuple[np.ndarray, np.ndarray]:
    """Bang-bang AC: full power in an occupied slot when the room starts the slot above comfort_max."""
    temps, p_cool = np.empty(SLOTS + 1), np.zeros(SLOTS)
    temps[0] = t0
    for k in range(SLOTS):
        p_cool[k] = params.p_cool_max_kw if occupied[k] and temps[k] > params.comfort_max_c else 0.0
        temps[k + 1] = thermal.simulate(params, np.full(SLOTS, t_out[k]), np.full(SLOTS, gains[k]),
                                        np.r_[p_cool[k], np.zeros(SLOTS - 1)], temps[k])[1]
    return temps, p_cool


def main() -> int:
    import matplotlib.pyplot as plt

    from b2g.data.plots import ACTUAL, FORECAST, GRID, TEXT_2, _save, _style

    cfg = load_config()
    params = thermal.ThermalParams.from_config(cfg)
    df = load_dataset(REPO_ROOT / cfg["data"]["processed_dir"])
    hottest = df.groupby("date")["temp_actual_c"].max().idxmax()
    day = df[df["date"] == hottest]
    occupied = thermal.occupancy(params, day.index[0].date(), cfg["base_load"]["weekend_days"])
    t_out = day["temp_actual_c"].to_numpy()
    gains = thermal.heat_gains_kw(params, day["ghi_actual_wm2"].to_numpy(), occupied)

    off = thermal.simulate(params, t_out, gains, np.zeros(SLOTS), params.t_initial_c)
    on, p_cool = thermostat(params, t_out, gains, occupied, params.t_initial_c)

    _style()
    hours = np.arange(SLOTS + 1) * DT_H
    fig, ax = plt.subplots(figsize=(10, 4.5))
    for k in np.nonzero(occupied)[0]:
        ax.axvspan(k * DT_H, (k + 1) * DT_H, ymin=0, ymax=1, color=GRID, alpha=0.5, linewidth=0)
    ax.axhspan(params.comfort_min_c, params.comfort_max_c, color=ACTUAL, alpha=0.08, linewidth=0)
    ax.plot(hours[:-1] + DT_H / 2, t_out, color=TEXT_2, linestyle="--", linewidth=1.2, label="Outdoor (actual)")
    ax.plot(hours, off, color=FORECAST, label="Room, AC off")
    ax.plot(hours, on, color=ACTUAL, label="Room, simple thermostat")
    ax.set_title(f"Room temperature on the hottest day, {hottest}")
    ax.set_xlabel("Hour of day (grey = someone home; blue band = comfort range)")
    ax.set_ylabel("°C")
    ax.set_xticks(range(0, 25, 3))
    ax.legend(loc="upper left", fontsize=8)
    path = _save(fig, REPO_ROOT / cfg["data"]["figures_dir"] / "m4_thermal_demo.png")

    print(f"Hottest day {hottest}: outdoor {t_out.min():.1f}-{t_out.max():.1f} degC")
    print(f"  AC off:     room {off.min():.1f}-{off.max():.1f} degC, "
          f"discomfort {thermal.comfort_violation_degree_hours(params, off, occupied):.1f} degC*h")
    print(f"  thermostat: room {on.min():.1f}-{on.max():.1f} degC, "
          f"discomfort {thermal.comfort_violation_degree_hours(params, on, occupied):.1f} degC*h, "
          f"AC {p_cool.sum() * DT_H:.1f} kWh")
    print(f"Saved {path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
