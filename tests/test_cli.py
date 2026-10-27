"""Tests for b2g.cli: options, LLM configuration and the run summary. No network, no LLM calls."""

import json
from pathlib import Path

import pytest

from b2g import cli
from b2g.agents import llm_client
from b2g.agents.llm_client import LLMSettings, LLMStats

ROOT = Path(__file__).resolve().parent.parent
REFERENCE_PRICES = json.loads((ROOT / "test_prices_reference.json").read_text())


def schedule(start: int, duration: int) -> list[int]:
    """96-slot on/off array that is ON from `start` for `duration` slots."""
    return [1 if start <= t < start + duration else 0 for t in range(96)]


@pytest.fixture
def settings(tmp_path):
    return LLMSettings(provider="groq", base_url="https://fake/v1", api_key="k", model="m",
                       run_id="r1", results_dir=tmp_path)


def test_parse_args_defaults():
    args = cli.parse_args([])
    assert (args.system, args.request, args.provider, args.model, args.cache) == (
        "S0", cli.DEFAULT_REQUEST, None, None, "on")
    s4 = cli.parse_args(["--system", "S4"])
    assert (s4.request, s4.date, s4.pv_forecaster) == (cli.DEMO_REQUEST, cli.DEMO_DATE, "lgbm")


def test_configure_llm_applies_overrides(monkeypatch):
    monkeypatch.setattr(llm_client, "load_env", lambda: None)  # ignore the real .env
    # configure_llm writes os.environ; give it a throwaway copy so nothing leaks into other tests
    monkeypatch.setattr(cli.os, "environ", {"OPENROUTER_API_KEY": "o", "OPENROUTER_MODEL": "from-env"})
    args = cli.parse_args(["--provider", "openrouter", "--model", "cli-model", "--cache", "off", "--run-id", "x"])
    try:
        settings = cli.configure_llm(args)
        assert (settings.provider, settings.api_key, settings.model) == ("openrouter", "o", "cli-model")
        assert (settings.cache_mode, settings.run_id) == ("off", "x")
        assert llm_client.get_client().settings == settings
        assert cli.os.environ["CEREBRAS_MODEL_OVERRIDE"] == "cli-model"  # what the original orchestrator reads
    finally:
        llm_client.set_client(None)


def test_start_slots_reads_first_on_slot():
    executed = [{"appliance_id": "dishwasher", "schedule": schedule(11, 6)},
                {"appliance_id": "ev_charger", "schedule": schedule(1, 24)}]
    assert cli.start_slots(executed) == {"dishwasher": 11, "ev_charger": 1}


def test_optimal_start_slots_on_reference_prices():
    assert cli.optimal_start_slots(REFERENCE_PRICES["prices"]) == {"washing_machine": 10, "dishwasher": 11, "ev_charger": 1}


def test_summary_matches_optimizer(settings):
    context = {"prices_data": REFERENCE_PRICES, "executed_schedules": [
        {"appliance_id": "washing_machine", "schedule": schedule(10, 8)},
        {"appliance_id": "dishwasher", "schedule": schedule(11, 6)},
        {"appliance_id": "ev_charger", "schedule": schedule(1, 24)}]}
    result = {"success": True, "iterations": 9, "duration_seconds": 33.6, "total_usage": {"total_tokens": 100}}
    summary = cli.build_summary(cli.parse_args([]), settings, result, context, LLMStats().as_dict())
    assert summary["matches_optimizer"] is True and summary["missing_appliances"] == []
    assert (summary["provider"], summary["model"], summary["run_id"]) == ("groq", "m", "r1")


def test_summary_reports_missing_appliance_after_failed_run(settings):
    """Like the gpt-oss-120b run in M0: two appliances scheduled, the EV never was."""
    context = {"prices_data": REFERENCE_PRICES, "executed_schedules": [
        {"appliance_id": "washing_machine", "schedule": schedule(10, 8)},
        {"appliance_id": "dishwasher", "schedule": schedule(11, 6)}]}
    result = {"success": False, "error": "API Error: 429"}
    summary = cli.build_summary(cli.parse_args([]), settings, result, context, LLMStats().as_dict())
    assert summary["matches_optimizer"] is False
    assert summary["missing_appliances"] == ["ev_charger"]
    assert summary["error"] == "API Error: 429"


def test_summary_without_prices_has_no_comparison(settings):
    summary = cli.build_summary(cli.parse_args([]), settings, {"success": False}, {}, LLMStats().as_dict())
    assert summary["optimal_start_slots"] is None and summary["matches_optimizer"] is False
