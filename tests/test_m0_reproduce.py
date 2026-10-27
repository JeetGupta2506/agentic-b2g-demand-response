"""M0: the original system runs without an ENTSO-E key and matches the baseline optimizer.

All times are 15-min slots (slot 0 = 00:00, 96 slots per day). Prices are EUR/MWh.
The LLM run is not executed here (it costs API calls); we check the JSON log that
`python orchestrator_agent_react.py "..."` saves under data/runs/<model>/.
"""

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Optimal start slots for test_prices_reference.json, EV ready by 07:00 (slot 28)
EXPECTED_START_SLOTS = {"washing_machine": 10, "dishwasher": 11, "ev_charger": 1}


def _load_optimizer():
    """Import milp-baseline/optimizer.py (the hyphen in the folder name blocks a normal import)."""
    spec = importlib.util.spec_from_file_location("optimizer", ROOT / "milp-baseline" / "optimizer.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _latest_run_file() -> Path | None:
    """Return the most recent saved orchestrator run log, or None if no run exists yet."""
    # rglob: model names like "openai/gpt-oss-120b" create nested folders
    runs = sorted((ROOT / "data" / "runs").rglob("run_*.json"), key=lambda p: p.name)
    return runs[-1] if runs else None


def test_config_loads_without_entsoe_key(monkeypatch):
    """config.py must not raise when ENTSOE_API_KEY is missing (sample prices are used instead)."""
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: None)  # ignore the real .env
    # Clean environment: only the original's Cerebras key, no ENTSO-E key, no provider settings
    monkeypatch.setattr(os, "environ", {"CEREBRAS_API_KEY": "dummy-key-for-test"})
    monkeypatch.delitem(sys.modules, "config", raising=False)

    import config

    assert config.ENTSOE_API_KEY is None
    assert config.LLM_SETTINGS.provider == "cerebras"  # original default still holds


def test_sample_prices_equal_reference_prices():
    """Without ENTSO-E the agents see data/prices_sample.json; the baseline uses test_prices_reference.json."""
    sample = json.loads((ROOT / "data" / "prices_sample.json").read_text())
    reference = json.loads((ROOT / "test_prices_reference.json").read_text())
    assert len(sample["prices"]) == 96
    assert sample["prices"] == reference["prices"]


def test_baseline_optimizer_start_slots():
    """The exhaustive-search baseline finds the known optimal start slot for each appliance."""
    optimizer = _load_optimizer()
    prices, _ = optimizer.load_reference_prices()
    results = optimizer.optimize_all_appliances(prices)
    assert {name: r["optimal_slot"] for name, r in results.items()} == EXPECTED_START_SLOTS


def test_llm_run_matches_baseline():
    """The latest saved LLM run scheduled all three appliances at the baseline's optimal slots."""
    run_file = _latest_run_file()
    if run_file is None:
        pytest.skip("No LLM run saved yet: run `python orchestrator_agent_react.py \"Schedule all flexible loads for minimal cost\"`")

    run = json.loads(run_file.read_text())
    reference = json.loads((ROOT / "test_prices_reference.json").read_text())
    assert run["prices_data"]["prices"] == reference["prices"], f"{run_file.name} used different prices"

    start_slots = {s["appliance_id"]: s["schedule"].index(1) for s in run["executed_schedules"]}
    assert start_slots == EXPECTED_START_SLOTS, f"{run_file.name} ({run['model']}) differs from baseline"
