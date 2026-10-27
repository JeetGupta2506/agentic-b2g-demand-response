"""Tests for M8: the demo runner (scripted LLM, no network) and the Streamlit app on the pre-run examples."""

import json
from datetime import date

import pytest

from b2g import REPO_ROOT
from b2g.cli import DEMO_REQUEST
from b2g.config import load_config
from b2g.demo import core
from b2g.demo.core import EXAMPLES, load_examples, run_example, save_example, slug


class ScriptedLLM:
    """Scripted orchestrator and agent answers by tag; anything else (S3) gets a greedy schedule."""

    def __init__(self, orchestrator, agents):
        self.scripts = {"s4:orchestrator": list(orchestrator), **{f"s4:{k}": list(v) for k, v in agents.items()}}

    def complete(self, payload, timeout=60, tag=""):
        if tag in self.scripts:
            content = self.scripts[tag].pop(0)
        else:
            content = json.dumps({"ev_kw": [7.4] * 24, "ac_kw": [1.6] * 24, "battery_kw": [0] * 24, "reasoning": "x"})
        return {"choices": [{"message": {"content": content}}], "usage": {"total_tokens": 10}}


SCRIPT = ["ACTION: CALL_AGENT | agent_name=ev_agent | user_request=leaving at 7, car at 90%",
          "ACTION: CALL_AGENT | agent_name=precool_agent | user_request=home from 2 pm, under 26",
          "ACTION: CALL_AGENT | agent_name=battery_agent | user_request=keep 30%",
          "ACTION: RUN_SOLVER", "ACTION: VERIFY"] + [
          "ACTION: FINISH | summary=The car leaves at 07:00 with 36 kWh."] * 2   # 2nd if a rewrite is asked
AGENTS = {"ev_agent": ['{"departure_time": "07:00", "target_soc": 0.9}'],
          "precool_agent": ['{"comfort_max_c": 26, "away_until": "14:00"}'], "battery_agent": ['{"reserve_soc": 0.3}']}


def test_examples_are_test_period_days():
    end = date.fromisoformat(load_config()["forecasting"]["test_end"])
    assert all(date(2026, 1, 1) <= date.fromisoformat(d) <= end for _, d, _ in EXAMPLES)
    assert len({slug(t) for t, _, _ in EXAMPLES}) == len(EXAMPLES)


def test_run_example_collects_plan_comparison_and_series(tmp_path, monkeypatch):
    data = run_example("2026-05-06", DEMO_REQUEST, "Test", with_s3=True, client=ScriptedLLM(SCRIPT, AGENTS))
    assert data["ok"] and data["constraints"]["ev"] == {"departure_time": "07:00", "target_soc": 0.9}
    assert set(data["comparison"]) == {"S1 simple rules", "S4 our system", "S5 perfect knowledge", "S3 pure LLM"}
    s = data["series"]
    assert len(s["pv"]) == len(s["ev"]) == 96 and len(s["temps"]) == len(s["e_ev"]) == 97
    assert data["comparison"]["S5 perfect knowledge"]["total_cost"] <= data["comparison"]["S4 our system"]["total_cost"] + 1e-6
    assert data["s3"]["errors"] > 0                      # the greedy schedule breaks the rules
    monkeypatch.setattr(core, "DEMO_DIR", tmp_path)
    save_example(data, name="custom_x")
    assert load_examples()[0]["comparison"] == json.loads(json.dumps(data["comparison"]))


@pytest.mark.skipif(not all((core.DEMO_DIR / f"{slug(t)}.json").exists() for t, _, _ in EXAMPLES),
                    reason="pre-run examples missing (python -m b2g.demo.precompute)")
def test_app_renders_every_tab_from_the_pre_run_examples():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(REPO_ROOT / "app.py"), default_timeout=60).run()
    assert not app.exception
    assert len(app.tabs) == 4 and len(app.metric) >= 8
    for title, _, _ in EXAMPLES:                          # every example renders in "Ask" and "Compare"
        app.selectbox[0].set_value(title)
        app.selectbox(key="compare").set_value(title)
        app.run()
        assert not app.exception and not any("did not finish" in e.value for e in app.error)


# --- live server (b2g.demo.server) ----------------------------------------------------------

@pytest.fixture
def server(tmp_path, monkeypatch):
    from b2g.demo.server import create_app
    monkeypatch.setattr(core, "DEMO_DIR", tmp_path / "demo")
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("<h1>demo</h1>", encoding="utf-8")
    (site / "404.html").write_text("missing", encoding="utf-8")
    return create_app(site, client=ScriptedLLM(SCRIPT, AGENTS)).test_client()


def test_server_serves_the_site_and_reports_health(server):
    assert server.get("/").data == b"<h1>demo</h1>"
    assert server.get("/nope.js").status_code == 404
    health = server.get("/api/health").get_json()
    assert health["live"] and health["first_day"] == "2026-01-01" and health["last_day"] == "2026-09-30"
    assert "api_key" not in json.dumps(health)


def test_server_rejects_bad_input(server):
    assert server.post("/api/plan", json={"date": "2025-05-06", "request": "hello there"}).status_code == 400   # not a test day
    assert server.post("/api/plan", json={"date": "06-05-2026", "request": "hello there"}).status_code == 400
    assert server.post("/api/plan", json={"date": "2026-05-06", "request": ""}).status_code == 400


def test_server_plans_a_live_request(server):
    r = server.post("/api/plan", json={"date": "2026-05-06", "request": DEMO_REQUEST})
    data = r.get_json()
    assert r.status_code == 200 and data["ok"] and data["title"] == "Your request"
    assert set(data["comparison"]) == {"S1 simple rules", "S4 our system", "S5 perfect knowledge"}
    assert len(list((core.DEMO_DIR / "live").glob("*.json"))) == 1
    assert load_examples() == []                         # live runs never mix with the pre-run examples
