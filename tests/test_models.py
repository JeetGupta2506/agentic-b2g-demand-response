"""Tests for the M4 physical models: energy conservation, limits, thermal behaviour, power balance."""

from datetime import date

import numpy as np
import pytest

from b2g.config import load_config
from b2g.models import DT_H, SLOTS, battery, ev, hhmm_to_slot, site, thermal

CFG = load_config()
WEEKEND = CFG["base_load"]["weekend_days"]
BAT = battery.BatteryParams.from_config(CFG)
CAR = ev.EVParams.from_config(CFG)
ROOM = thermal.ThermalParams.from_config(CFG)
GRID = site.GridParams.from_config(CFG)
WEEKDAY, SATURDAY = date(2026, 5, 6), date(2026, 5, 9)  # a Wednesday and a Saturday


def profile(value=0.0, slots=None):
    """96-slot array: `value` in the given slot range (or everywhere), 0 elsewhere."""
    p = np.zeros(SLOTS)
    if slots is None:
        p[:] = value
    else:
        p[slots] = value
    return p


def test_hhmm_to_slot():
    assert (hhmm_to_slot("00:00"), hhmm_to_slot("08:00"), hhmm_to_slot("18:15"), hhmm_to_slot("24:00")) == (0, 32, 73, 96)
    with pytest.raises(ValueError):
        hhmm_to_slot("08:10")


def test_config_values_load():
    assert (BAT.e_min_kwh, BAT.e_max_kwh, BAT.e_initial_kwh) == pytest.approx((1.0, 10.0, 5.0))
    assert CAR.target_kwh == pytest.approx(32.0)
    assert GRID.import_limit_kw == 8.0


# --- battery --------------------------------------------------------------------------------

def test_battery_charge_adds_eta_times_energy():
    energy = battery.simulate(BAT, profile(1.0, slice(0, 4)), profile(), e0_kwh=5.0)  # 1 kW for 1 h
    assert energy.shape == (SLOTS + 1,)
    assert energy[4] == pytest.approx(5.0 + 0.95)
    assert energy[-1] == pytest.approx(5.95)


def test_battery_round_trip_loses_energy():
    charge, discharge = profile(2.0, slice(0, 8)), profile(0.0)
    stored = battery.simulate(BAT, charge, discharge, 2.0)[8] - 2.0      # 4 kWh in -> 3.8 stored
    discharge[8:16] = stored * BAT.eta_discharge / (8 * DT_H)             # deliver everything back out
    energy = battery.simulate(BAT, charge, discharge, 2.0)
    delivered = discharge.sum() * DT_H
    assert energy[16] == pytest.approx(2.0)
    assert delivered / (charge.sum() * DT_H) == pytest.approx(0.95 * 0.95)


def test_battery_check_catches_every_limit():
    assert battery.check(BAT, profile(), profile(), 5.0) == []
    over_power = battery.check(BAT, profile(6.0, slice(0, 1)), profile(), 5.0)
    assert any("charge 6.000 kW > max" in p for p in over_power)
    overfull = battery.check(BAT, profile(5.0, slice(0, 8)), profile(), 5.0)  # +9.5 kWh
    assert any("> max 10.000 kWh" in p for p in overfull)
    empty = battery.check(BAT, profile(), profile(5.0, slice(0, 4)), 5.0)    # -5.26 kWh
    assert any("< min 1.000 kWh" in p for p in empty)
    both = battery.check(BAT, profile(1.0, slice(3, 4)), profile(1.0, slice(3, 4)), 5.0)
    assert any("same time" in p for p in both)


def test_battery_clip_is_feasible_and_keeps_feasible_plans():
    rng = np.random.default_rng(0)
    pc, pd_ = rng.uniform(0, 8, SLOTS), rng.uniform(0, 8, SLOTS)
    clipped_c, clipped_d, energy = battery.clip_to_feasible(BAT, pc, pd_, 5.0)
    assert battery.check(BAT, clipped_c, clipped_d, 5.0) == []
    np.testing.assert_allclose(energy, battery.simulate(BAT, clipped_c, clipped_d, 5.0))
    feasible_c, feasible_d = profile(2.0, slice(40, 48)), profile(1.5, slice(72, 80))
    out_c, out_d, _ = battery.clip_to_feasible(BAT, feasible_c, feasible_d, 5.0)
    np.testing.assert_allclose(out_c, feasible_c)
    np.testing.assert_allclose(out_d, feasible_d)


# --- EV -------------------------------------------------------------------------------------

def test_ev_day_weekday_and_weekend():
    weekday = ev.ev_day(CAR, WEEKDAY, WEEKEND)
    assert (weekday.departure_slot, weekday.arrival_slot) == (32, 72)
    assert weekday.at_home[:32].all() and not weekday.at_home[32:72].any() and weekday.at_home[72:].all()
    weekend = ev.ev_day(CAR, SATURDAY, WEEKEND)
    assert weekend.at_home.all() and weekend.departure_slot is None and weekend.trip_kwh == 0


def test_ev_charging_trip_and_target():
    day = ev.ev_day(CAR, WEEKDAY, WEEKEND)
    p = profile(7.4, slice(0, 8))                      # 2 h overnight: +13.6 kWh at 92 %
    energy = ev.simulate(CAR, day, p, e0_kwh=16.0)
    assert energy[32] == pytest.approx(16.0 + 0.92 * 7.4 * 2)
    assert energy[72] == pytest.approx(energy[32] - 16.0)   # trip removed on arrival
    assert ev.unmet_energy_kwh(CAR, day, p, 16.0) == pytest.approx(32.0 - energy[32])
    assert ev.unmet_energy_kwh(CAR, day, profile(7.4, slice(0, 12)), 16.0) == 0.0


def test_ev_check_flags_away_charging_and_overfill():
    day = ev.ev_day(CAR, WEEKDAY, WEEKEND)
    away = ev.check(CAR, day, profile(3.0, slice(40, 41)), 35.0)
    assert any("while the car is away" in p for p in away)
    overfull = ev.check(CAR, ev.ev_day(CAR, SATURDAY, WEEKEND), profile(7.4, slice(0, 20)), 35.0)
    assert any("> capacity" in p for p in overfull)
    assert ev.check(CAR, day, profile(7.4, slice(0, 12)), 16.0) == []


def test_ev_clip_respects_availability_and_capacity():
    day = ev.ev_day(CAR, WEEKDAY, WEEKEND)
    p, energy = ev.clip_to_feasible(CAR, day, profile(10.0), 30.0)
    assert (p[~day.at_home] == 0).all() and p.max() <= CAR.p_max_kw + 1e-9
    assert energy.max() <= CAR.capacity_kwh + 1e-9
    assert ev.check(CAR, day, p, 30.0) == []


# --- thermal --------------------------------------------------------------------------------

def test_one_thermal_step_by_hand():
    t_out, gains, p_cool = profile(35.0), profile(0.5), profile(1.0, slice(0, 1))
    temps = thermal.simulate(ROOM, t_out, gains, p_cool, t0_c=26.0)
    heat = (35 - 26) / 3.0 + 0.5 - 3.3 * 1.0               # kW
    assert temps[1] == pytest.approx(26.0 + 0.25 / 8.0 * heat)


def test_room_warms_without_ac_towards_steady_state():
    t_out, gains = profile(35.0), profile(0.3)
    temps = thermal.simulate(ROOM, t_out, gains, profile(), t0_c=25.0)
    assert (np.diff(temps) > 0).all()                       # always warming
    steady = thermal.steady_state_c(ROOM, 35.0, 0.3, 0.0)   # 35 + 3 * 0.3 = 35.9
    assert steady == pytest.approx(35.9)
    assert temps[-1] < steady
    expected = steady - (steady - 25.0) * (1 - DT_H / (ROOM.r_c_per_kw * ROOM.c_kwh_per_c)) ** SLOTS
    assert temps[-1] == pytest.approx(expected)              # exact solution of the discrete model
    assert 0.3 < (temps[4] - temps[0]) < 0.5                 # ~0.4 degC in the first hour


def test_ac_on_cools_the_room():
    temps = thermal.simulate(ROOM, profile(35.0), profile(0.3), profile(ROOM.p_cool_max_kw), t0_c=30.0)
    assert (np.diff(temps) < 0).all()
    assert thermal.steady_state_c(ROOM, 35.0, 0.3, ROOM.p_cool_max_kw) < ROOM.comfort_min_c


def test_occupancy_and_gains():
    weekday, saturday = thermal.occupancy(ROOM, WEEKDAY, WEEKEND), thermal.occupancy(ROOM, SATURDAY, WEEKEND)
    assert weekday[:32].all() and not weekday[32:72].any() and weekday[72:].all() and saturday.all()
    gains = thermal.heat_gains_kw(ROOM, profile(1000.0), weekday)
    assert gains[0] == pytest.approx(1.5 + 0.3) and gains[40] == pytest.approx(1.5)


def test_comfort_degree_hours_only_when_occupied():
    temps = np.full(SLOTS + 1, 25.0)
    occupied = np.ones(SLOTS, dtype=bool)
    assert thermal.comfort_violation_degree_hours(ROOM, temps, occupied) == 0.0
    temps[1:5] = 29.0                                        # 2 degC too warm for 1 h
    assert thermal.comfort_violation_degree_hours(ROOM, temps, occupied) == pytest.approx(2.0)
    occupied[0:4] = False
    assert thermal.comfort_violation_degree_hours(ROOM, temps, occupied) == 0.0
    temps[10] = 22.0                                         # 2 degC too cold for 15 min
    assert thermal.comfort_violation_degree_hours(ROOM, temps, np.ones(SLOTS, dtype=bool)) == pytest.approx(2.0 + 0.5)


def test_thermal_check_limits():
    temps = np.full(SLOTS + 1, 25.0)
    assert thermal.check(ROOM, temps, np.ones(SLOTS, dtype=bool), profile(1.0)) == []
    assert any("outside 0..1.6" in p for p in thermal.check(ROOM, temps, None, profile(2.0, slice(0, 1))))
    temps[50] = 19.0
    assert any("below the AC's minimum" in p for p in thermal.check(ROOM, temps, None, profile()))


def test_unstable_thermal_parameters_rejected():
    bad = {**CFG, "thermal": {**CFG["thermal"], "r_c_per_kw": 0.01, "c_kwh_per_c": 0.01}}
    with pytest.raises(ValueError):
        thermal.ThermalParams.from_config(bad)


# --- site balance ---------------------------------------------------------------------------

def test_power_balance_adds_up_and_never_imports_and_exports_together():
    rng = np.random.default_rng(1)
    base, pv, p_ev, cool, pc, pd_ = (rng.uniform(0, 4, SLOTS) for _ in range(6))
    net = site.net_load_kw(base, pv, p_ev, cool, pc, pd_)
    g_imp, g_exp = site.grid_flows(net)
    np.testing.assert_allclose(g_imp - g_exp, base + p_ev + cool + pc - pd_ - pv)
    assert ((g_imp > 0) & (g_exp > 0)).sum() == 0
    assert (g_imp >= 0).all() and (g_exp >= 0).all()


def test_import_limit_cost_peak_and_self_consumption():
    g_imp = profile(9.0, slice(76, 77))
    assert len(site.check_import_limit(GRID, g_imp)) == 1
    price, g_exp = profile(8.0), profile(2.0, slice(40, 44))
    assert site.daily_cost(price, g_imp, g_exp, export_price=2.5) == pytest.approx(9 * 8 * 0.25 - 2 * 2.5 * 1.0)
    assert site.peak_import_kw(g_imp) == 9.0
    pv = profile(4.0, slice(40, 44))                          # 4 kWh of PV, 2 kWh exported
    assert site.self_consumption_pct(pv, g_exp) == pytest.approx(50.0)
    assert np.isnan(site.self_consumption_pct(profile(), profile()))


def test_coupling_ev_and_ac_can_exceed_the_grid_limit():
    """The reason loads must be coordinated: EV + AC + evening base load > 8 kW without PV."""
    g_imp, _ = site.grid_flows(site.net_load_kw(profile(0.9), profile(), p_ev=profile(CAR.p_max_kw), p_cool=profile(ROOM.p_cool_max_kw)))
    assert site.check_import_limit(GRID, g_imp)
