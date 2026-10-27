# CLAUDE.md — B2G Agentic Demand Response (SVNIT research project)

## What this project is
A 3-person B.Tech AI research project at SVNIT Surat. Course topic:
"Building-to-Grid (B2G) Demand Response via Predictive AI — forecast local renewable
availability and shift smart-building loads (EV charging, battery storage, pre-cooling)
to support local microgrids."

We extend the open-source repo of our base paper:
El Makroum, Zwickl-Bernhard, Kranzl (2025), "Agentic AI Home Energy Management System:
A Large Language Model Framework for Residential Load Scheduling", arXiv:2510.26603.
Repo: https://github.com/RedaElMakroum/agentic-ai-hems (MIT). This repo is our fork of it.

Our contribution (one line): a forecast-aware, hybrid agentic system — LLM agents
understand the request and set goals/constraints, a MILP solver computes the schedule,
a verifier checks physical limits and triggers replanning — coordinating EV, battery and
pre-cooling under shared solar and a grid import limit, evaluated over many days.

**Full spec, milestones and acceptance criteria: `docs/B2G_PLAN.md`. Read it before any work.**

## How to work with me (the user)
- Work ONE milestone at a time, in the order in `docs/B2G_PLAN.md`. Before coding a
  milestone, show a short plan (files to add/change, approach) and wait for approval.
- At the end of each milestone: run the tests, show results, tick the milestone's
  checkbox in `docs/B2G_PLAN.md`, and add any design decision to `docs/DECISIONS.md`
  (date, decision, why).
- I am new to this field. When you finish a milestone, explain in plain words what was
  built and why it matters for the research, in 5–10 lines.
- Ask before: deleting files, large refactors, adding heavy dependencies (anything that
  needs a GPU or > ~500 MB), or changing the original paper's files beyond what the plan lists.

## Hard rules
- Everything must run on a student laptop CPU. GPU is optional, never required.
- Never commit secrets. Keys live in `.env` (gitignored). Keep `.env.example` updated.
- Do not break the original system: the base paper's behaviour must still be
  reproducible (it is our baseline). New code goes in the `b2g/` package.
- Deterministic experiments: fixed random seeds, LLM temperature 0, log every LLM run
  (prompt, response, tokens, latency) to `results/runs/` as JSON. Cache LLM responses by
  prompt hash so re-running an experiment does not re-spend API calls.
- Evaluate schedules against ACTUAL data, never against the forecast the plan was made with.
- Physical numbers (battery size, tariffs, thermal parameters) are placeholders in
  `b2g/config/default.yaml`. Never hard-code them in logic.
- Python 3.11+, type hints, small functions, docstrings stating units (kW, kWh, °C, 15-min slots).
- Tests in `tests/` with pytest. Every physical model, the solver and the verifier need tests.

## Facts about the original repo (verified)
- Entry point: `orchestrator_agent_react.py` (ReAct loop; actions written as
  `ACTION: NAME | key=value`). Tools in `tools.py`. Appliance specs in `config.py`.
  Agent prompts are the `*_agent.md` files and `hems_orchestrator.md`. API: `api.py`
  (Flask) + `dashboard.html`.
- Time grid: 96 slots of 15 min per day. Prices from ENTSO-E (Austria) with fallback to
  `data/prices_sample.json`.
- The LLM base URL is hard-coded to Cerebras in `orchestrator_agent_react.py`, although
  the README claims provider-agnostic support.
- `config.py` raises an error if `ENTSOE_API_KEY` is missing, even though `tools.py`
  falls back to sample prices.
- Google Calendar is optional: without `credentials.json` the EV uses a default deadline.
- `milp-baseline/optimizer.py` is an exhaustive window search with numpy, not a true MILP.
- `tools.py` contains an unfinished heat-pump HEATING model (`calculate_heating_requirement`,
  RC thermal model) that is not registered in `config.py` and not in the paper.
- Appliances: washing machine 2.0 kW / 120 min, dishwasher 1.8 kW / 90 min,
  EV charger 7.4 kW / 360 min, all binary on/off and independent of each other.

## Commands (keep this section updated as the project grows)
- Venv (Windows, Python 3.11): `py -3.11 -m venv .venv` then `.venv\Scripts\activate`
- Install: `pip install -r requirements.txt -r requirements-api.txt -r requirements-b2g.txt`
- Tests: `pytest -q`
- Headless run (preferred): `python -m b2g.cli --system S0` (options: `--provider groq|openrouter|cerebras|ollama`,
  `--model`, `--cache on|off|refresh`, `--run-id`). Writes `results/runs/<run_id>/summary.json` and `llm_calls.jsonl`;
  LLM answers are cached in `results/cache/`, so a repeated run costs 0 tokens.
- LLM provider: `LLM_PROVIDER` in `.env`; each provider has its own `<PROVIDER>_API_KEY` / `<PROVIDER>_MODEL`.
  All LLM calls go through `b2g/agents/llm_client.py`.
- Data (M2): `python -m b2g.data.build` → `data/b2g/processed/site_15min.csv` (+ `_meta.json`) and
  `results/figures/m2_*.png`. Settings in `b2g/config/default.yaml`; Open-Meteo downloads cached in `data/b2g/raw/`.
  Load in code with `b2g.data.build.load_dataset()`.
- Forecasts (M3): `python -m b2g.forecasting.train` (~25 s) → `data/b2g/processed/forecasts.csv` (all models,
  val + test days), `results/m3_forecast_metrics.{csv,md}`, `results/m3_lgbm_info.json`, `results/figures/m3_*.png`.
  Re-score without training: `python -m b2g.forecasting.evaluate`.
- Physical models (M4): `b2g/models/` (battery, ev, thermal, site; each has simulate/check, battery+EV
  have clip_to_feasible). Thermal sanity figure: `python -m b2g.models.demo`.
- Baselines (M5): `python -m b2g.eval.compare_baselines [--start YYYY-MM-DD --days N]` (~12 s for 7 days) →
  `results/m5_baselines.{csv,md}`, `results/figures/m5_oracle_day.png`. Solver `b2g/solver/milp.py`
  (`solve_day`), settlement `b2g/sim/simulate.py` (`settle`, `run_days`), systems in `b2g/baselines/`.
- Agents S4 (M6): `python -m b2g.cli --system S4 --date 2026-05-06 --request "..."` (default request = demo) →
  `results/runs/<run>/trace.md` (readable), `trace.json`, `summary.json` (plan + outcome on the actual day).
  Code: `b2g/agents/{orchestrator,schemas,apply,tools}.py`, prompts in `b2g/agents/prompts/`.
- Verifier (M7): `b2g/verifier/checks.py` (`verify`, `check_explanation`), `request_facts.py`. S4 uses it by
  default (`--no-verify` = M6 behaviour). Pure LLM S3: `python -m b2g.cli --system S3 [--date --request]`
  (`b2g/baselines/pure_llm.py`; judged against `cli.demo_truth()` for the demo request, defaults otherwise).
- Demo app (M8): `python -m b2g.demo.precompute` once (runs the 4 example requests with the LLM, saves
  `results/demo/*.json`), then `streamlit run app.py`. Works offline from the pre-run examples. Code: `app.py`, `b2g/demo/`.
- Web data for a Next.js frontend: `python -m b2g.demo.export_web [--out web/public/data]` → `results/web_data/{site,examples,results}.json`;
  design prompt in `docs/FRONTEND_PROMPT.md`.
- Next.js site (built by Claude Design) in `web/`: `python -m b2g.demo.server` (Flask; serves `web/out/` + `/api/plan` for live
  requests, saved to `results/demo/live/`), open http://localhost:3000. Pre-run examples work offline; live typing needs internet + key. Rebuild after new data: copy `results/web_data/*.json` to `web/public/data/`, then in `web/`: `npm install`, `npm run build`.
- Original system (headless, as the paper ran it): `python orchestrator_agent_react.py "Schedule all flexible loads for minimal cost"`
  (needs `PYTHONUTF8=1` on Windows; log in `data/runs/<model>/run_*.json`; `tests/test_m0_reproduce.py` checks the latest one)
- Original system (dashboard): `python api.py` then `python -m http.server 8000`
