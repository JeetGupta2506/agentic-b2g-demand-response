"""Tests for M5: the MILP scheduler, settlement on actual data, S1 rules and multi-day runs."""

import dataclasses
from datetime import date

import numpy as np
import pytest

from b2g.baselines import forecast_milp, rule_based
from b2g.config import load_config
from b2g.models import DT_H, SLOTS, battery, ev, site, thermal
from b2g.models.site import GridParams
from b2g.sim.day import Actions, Assets, DayData, State, calendar
from b2g.sim.simulate import run_days, settle
from b2g.solver.milp import solve_day

CFG = load_config()
ASSETS = Assets.from_config(CFG)
WEDNESDAY, SATURDAY = date(2026, 5, 6), date(2026, 5, 9)


def flat(value, slots=None, base=0.0):
    p = np.full(SLOTS, float(base))
    p[slice(None) if slots is None else slots] = value
    return p


def day_data(day=WEDNESDAY, price=None, pv=None, base=0.5, t_out=25.0, ghi=0.0, source="test"):
    return DayData(day, flat(7.0) if price is None else price, flat(0.0) if pv is None else pv,
                   flat(base), flat(t_out), flat(ghi), source)


def plan_for(data, state=None, assets=ASSETS):
    ev_day, occupied = calendar(assets, data.day)
    return solve_day(assets, data, ev_day, occupied, state or State.initial(assets))


def test_plan_passes_every_physical_check_on_its_own_inputs():
    hot = flat(36.0, slice(40, 80), base=30.0)
    pv = 4.0 * np.clip(np.sin(np.pi * (np.arange(SLOTS) / 4 - 6.5) / 12), 0, None)
    data = day_data(price=flat(5.6, slice(36, 68), base=7.0), pv=pv, t_out=hot, ghi=pv * 200)
    state = State.initial(ASSETS)
    plan = plan_for(data, state)
    ev_day, occupied = calendar(ASSETS, data.day)
    a = plan.actions
    assert battery.check(ASSETS.battery, a.p_charge, a.p_discharge, state.e_bat_kwh) == []
    assert ev.check(ASSETS.ev, ev_day, a.p_ev, state.e_ev_kwh) == []
    assert thermal.check(ASSETS.thermal, plan.temps, occupied, a.p_cool) == []
    assert site.check_import_limit(ASSETS.grid, plan.grid_import) == []
    np.testing.assert_allclose(plan.e_bat, battery.simulate(ASSETS.battery, a.p_charge, a.p_discharge, state.e_bat_kwh), atol=1e-5)
    np.testing.assert_allclose(plan.e_ev, ev.simulate(ASSETS.ev, ev_day, a.p_ev, state.e_ev_kwh), atol=1e-5)
    gains = thermal.heat_gains_kw(ASSETS.thermal, data.ghi_wm2, occupied)
    np.testing.assert_allclose(plan.temps, thermal.simulate(ASSETS.thermal, data.t_out_c, gains, a.p_cool, state.t_room_c), atol=1e-5)
    assert plan.e_bat[-1] >= plan.e_bat[0] - 1e-6   # no draining the battery at midnight


def test_ev_charges_in_the_cheapest_slots():
    need_two_hours = ASSETS.ev.target_kwh - ASSETS.ev.eta_charge * ASSETS.ev.p_max_kw * 2
    plan = plan_for(day_data(price=flat(3.0, slice(0, 8), base=10.0)), State(5.0, need_two_hours, 25.0))
    assert plan.actions.p_ev[:8].sum() * DT_H == pytest.approx(ASSETS.ev.p_max_kw * 2, rel=1e-4)
    assert plan.actions.p_ev[8:32].sum() < 1e-4
    assert plan.ev_short_kwh == pytest.approx(0, abs=1e-6)


def test_grid_limit_is_respected_when_ev_and_ac_compete():
    hot_night = day_data(base=1.0, t_out=34.0)
    plan = plan_for(hot_night, State(1.0, 0.0, 28.0))   # empty battery and car, warm room
    assert plan.grid_import.max() <= ASSETS.grid.import_limit_kw + 1e-6
    both = (plan.actions.p_ev > 0.1) & (plan.actions.p_cool > 0.1)
    assert both.any() and (plan.actions.p_ev[both] < ASSETS.ev.p_max_kw - 0.1).any()   # EV slowed for the AC


def test_pre_cools_before_people_come_home_when_afternoon_is_cheap():
    hot = flat(36.0)
    cheap_afternoon = plan_for(day_data(price=flat(3.0, slice(48, 72), base=10.0), t_out=hot), State(5.0, 32.0, 27.0))
    flat_price = plan_for(day_data(price=flat(10.0), t_out=hot), State(5.0, 32.0, 27.0))
    away = slice(32, 72)   # weekday 08:00-18:00, nobody home
    assert cheap_afternoon.actions.p_cool[away].sum() > flat_price.actions.p_cool[away].sum() + 1
    assert cheap_afternoon.temps[72] < flat_price.temps[72] - 0.5   # cooler room at 18:00


def test_never_charges_and_discharges_in_the_same_slot():
    arbitrage = day_data(price=flat(2.0, slice(0, 24), base=12.0), t_out=25.0)
    plan = plan_for(arbitrage, State(5.0, 32.0, 25.0))
    a = plan.actions
    assert not ((a.p_charge > 1e-6) & (a.p_discharge > 1e-6)).any()
    assert a.p_discharge.sum() > 0   # it does use the battery


def test_impossible_ev_day_still_solves_and_reports_the_shortfall():
    weak_grid = dataclasses.replace(ASSETS, grid=GridParams(import_limit_kw=2.0, export_price=2.5))
    plan = plan_for(day_data(base=0.5), State(1.0, 0.0, 25.0), assets=weak_grid)   # empty car, 2 kW grid
    possible = (2.0 - 0.5) * 8 * ASSETS.ev.eta_charge    # 8 h of grid headroom before 08:00 (~11 kWh)
    assert plan.status.startswith("Optimal")
    assert plan.ev_short_kwh == pytest.approx(ASSETS.ev.target_kwh - plan.e_ev[32], abs=1e-5)
    assert plan.ev_short_kwh > ASSETS.ev.target_kwh - possible - 1
    assert plan.e_ev.min() >= -1e-9                       # came back empty, never negative


def test_solver_is_deterministic():
    data = day_data(price=flat(5.6, slice(36, 68), base=7.0), t_out=flat(35.0))
    a, b = plan_for(data), plan_for(data)
    np.testing.assert_array_equal(a.actions.p_ev, b.actions.p_ev)
    np.testing.assert_array_equal(a.actions.p_cool, b.actions.p_cool)


# --- settlement -----------------------------------------------------------------------------

def test_perfect_forecast_settles_exactly_as_planned():
    pv = 3.0 * np.clip(np.sin(np.pi * (np.arange(SLOTS) / 4 - 6.5) / 12), 0, None)
    data = day_data(pv=pv, t_out=flat(34.0), ghi=pv * 250)
    state = State.initial(ASSETS)
    plan = plan_for(data, state)
    result = settle(ASSETS, plan.actions, data, state)
    np.testing.assert_allclose(result.grid_import, plan.grid_import, atol=1e-5)
    np.testing.assert_allclose(result.temps, plan.temps, atol=1e-5)
    np.testing.assert_allclose(result.e_bat, plan.e_bat, atol=1e-5)
    assert result.violations == []


def test_less_sun_than_forecast_means_more_import():
    pv = 3.0 * np.clip(np.sin(np.pi * (np.arange(SLOTS) / 4 - 6.5) / 12), 0, None)
    forecast, cloudy = day_data(pv=pv), day_data(pv=pv * 0.3)
    plan = plan_for(forecast)
    planned = settle(ASSETS, plan.actions, forecast, State.initial(ASSETS))
    real = settle(ASSETS, plan.actions, cloudy, State.initial(ASSETS))
    assert real.metrics["import_kwh"] > planned.metrics["import_kwh"] + 1
    assert real.metrics["electricity_cost"] > planned.metrics["electricity_cost"]


def test_settlement_clips_impossible_battery_actions():
    greedy = Actions(flat(0.0), flat(5.0), flat(0.0), flat(0.0))   # discharge all day
    result = settle(ASSETS, greedy, day_data(), State.initial(ASSETS))
    assert result.e_bat.min() >= ASSETS.battery.e_min_kwh - 1e-9
    assert result.applied.p_discharge.sum() < greedy.p_discharge.sum()


def test_total_cost_adds_up():
    result = settle(ASSETS, Actions(flat(0.0), flat(0.0), flat(0.0), flat(0.0)), day_data(t_out=flat(36.0)), State(5.0, 10.0, 27.0))
    m = result.metrics
    assert m["comfort_dh"] > 0 and m["ev_unmet_kwh"] > 0 and m["violation"]
    assert m["total_cost"] == pytest.approx(m["electricity_cost"] + m["battery_wear_cost"] + m["comfort_penalty"] + m["ev_penalty"])


# --- S1 rules and multi-day runs ------------------------------------------------------------

def test_rule_based_behaviour():
    pv = 6.0 * np.clip(np.sin(np.pi * (np.arange(SLOTS) / 4 - 6.5) / 12), 0, None)
    data = day_data(pv=pv, base=0.5, t_out=flat(36.0))
    state = State(5.0, 16.0, 28.0)
    actions = rule_based.rule_based_actions(ASSETS, data, state, respect_limit=True)
    ev_day, occupied = calendar(ASSETS, data.day)
    assert actions.p_ev[0] > 0                                     # charges as soon as it can
    assert (actions.p_ev[~ev_day.at_home] == 0).all()
    assert (actions.p_cool[~occupied] == 0).all() and actions.p_cool[occupied].max() == ASSETS.thermal.p_cool_max_kw
    assert actions.p_charge[32:72].sum() > 0                       # stores daytime surplus (until full)
    result = settle(ASSETS, actions, data, state)
    assert result.grid_import.max() <= ASSETS.grid.import_limit_kw + 1e-6
    assert result.metrics["ev_unmet_kwh"] == pytest.approx(0, abs=1e-6)


def test_oracle_is_not_worse_than_rules_on_a_hot_day():
    pv = 4.0 * np.clip(np.sin(np.pi * (np.arange(SLOTS) / 4 - 6.5) / 12), 0, None)
    data = day_data(price=flat(5.6, slice(36, 68), base=7.0), pv=pv, base=0.6, t_out=flat(36.0), ghi=pv * 250)
    state = State.initial(ASSETS)
    rules = settle(ASSETS, rule_based.rule_based_actions(ASSETS, data, state), data, state)
    oracle = settle(ASSETS, plan_for(data, state).actions, data, state)
    assert oracle.metrics["total_cost"] <= rules.metrics["total_cost"] + 1e-6


def test_run_days_carries_actual_end_state_forward():
    data_for = lambda d: day_data(day=d, t_out=flat(33.0))
    results = run_days(ASSETS, "S5", forecast_milp.make_planner(ASSETS, data_for), data_for, WEDNESDAY, 3)
    assert [r.day for r in results] == [date(2026, 5, 6), date(2026, 5, 7), date(2026, 5, 8)]
    for before, after in zip(results, results[1:]):
        assert after.e_bat[0] == pytest.approx(before.end_state.e_bat_kwh)
        assert after.e_ev[0] == pytest.approx(before.end_state.e_ev_kwh)
        assert after.temps[0] == pytest.approx(before.end_state.t_room_c)
    assert all("solve_s" in r.metrics for r in results)
