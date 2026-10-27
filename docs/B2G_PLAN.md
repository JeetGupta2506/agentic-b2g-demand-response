# B2G Agentic Demand Response — Build Plan

Place this file at `docs/B2G_PLAN.md`. `CLAUDE.md` (repo root) points here.
Tick milestones as they are completed. Record decisions in `docs/DECISIONS.md`.

---

## 1. Research framing

**Working title:** Forecast-Aware Hybrid Agentic AI for Building-to-Grid Demand Response
with EV, Battery and Pre-Cooling Coordination.

**Base paper gaps we address** (most are from the paper's own limitations, Section 4.6):

| # | Gap in base paper | Our fix |
|---|---|---|
| 1 | No thermal loads (AC / heat pump) | Pre-cooling agent + linear room-temperature (1R1C) model |
| 2 | No solar, no battery, no forecasting — price signal only | PV + battery models; ML forecaster for PV and base load |
| 3 | Appliances are independent; the "multi-appliance" problem splits into separate problems | Shared PV, one battery and a grid import limit couple all loads |
| 4 | LLM does the arithmetic itself; 2 of 3 models failed multi-appliance scheduling; no safety checks | LLM sets goals/constraints, MILP solver computes, verifier checks and triggers replanning |
| 5 | 1 day, 1 household, 75 runs; no deadline-vs-price conflicts | 30–60 days + conflict scenarios + request variations |
| 6 | Depends on a 70B model and very fast inference | Compare a large and a small (≈8B) model under each design |

**Research questions**
- RQ1: Does the hybrid design (LLM + solver + verifier) cut constraint violations and cost
  versus a pure-LLM scheduler, across model sizes?
- RQ2: How much of the oracle (perfect-forecast) performance does a forecast-driven
  system recover, and does forecast accuracy rank the same as decision cost?
- RQ3: How accurately do the LLM agents turn natural-language requests into correct
  constraints (departure time, target charge, comfort band)? This is the value an LLM
  adds over a plain optimizer.

---

## 2. System architecture

```
User request (natural language) ─┐
                                 ▼
Forecaster (PV + base load) ──► Orchestrator agent (ReAct loop)
                                 │  delegates
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
        EV agent          Battery agent      Pre-cooling agent
   (deadline, target)   (reserve, limits)   (comfort band, hours)
              └────────► constraint JSON ◄──────────┘
                                 ▼
                    Solver tool (PuLP MILP, joint)
                                 ▼
               Verifier (deterministic checks + LLM report)
                   │ fail: violations → orchestrator replans (max 3)
                   ▼ pass
           Final schedule + plain-language explanation
```

Agents never compute schedules by hand in the hybrid system. Specialist agents output
structured constraint JSON (validated with pydantic). The orchestrator merges them,
calls the solver, then the verifier.

### Orchestrator actions (same `ACTION: NAME | key=value` format as the original)
- `GET_FORECAST | date=YYYY-MM-DD` → PV, base-load, weather forecast (96 slots) + price vector
- `GET_CALENDAR_CONSTRAINT` → EV departure (reuse original; scenario file supplies it in experiments)
- `CALL_AGENT | agent_name=<ev_agent|battery_agent|precool_agent> | user_request=<text>` → constraint JSON
- `RUN_SOLVER` → schedule from merged constraints
- `VERIFY` → pass/fail + violation list
- `FINISH | summary=<text>`

---

## 3. Target repo layout (new code only; original files stay)

```
b2g/
  config/default.yaml        # site, assets, tariff, comfort, limits, llm, seeds
  data/                      # fetch_weather.py, prices.py, load_profiles.py, pv.py
  forecasting/               # baselines.py, lgbm.py, chronos.py (optional), train.py, evaluate.py
  models/                    # battery.py, ev.py, thermal.py, site.py (power balance)
  solver/milp.py             # joint MILP over 96 slots (PuLP + CBC)
  agents/                    # llm_client.py, orchestrator.py, tools.py, schemas.py, prompts/*.md
  verifier/checks.py         # deterministic physical + request-consistency checks
  sim/                       # simulate.py (settlement on actuals), scenarios.py, requests.py
  baselines/                 # rule_based.py, oracle.py, pure_llm.py
  eval/                      # run_experiments.py, metrics.py, plots.py
  cli.py                     # headless single-day run: python -m b2g.cli --date ... --system ...
tests/
data/b2g/                    # downloaded/processed data (raw gitignored)
results/                     # runs/ (gitignored), summary CSVs and figures (committed)
docs/B2G_PLAN.md, docs/DECISIONS.md
requirements-b2g.txt         # pulp, pandas, numpy, lightgbm, pydantic, pyyaml, matplotlib, pytest, openai
```

---

## 4. Modelling spec (all on 96 × 15-min slots, Δt = 0.25 h)

**Site (default):** Surat, India — lat 21.17, lon 72.83, timezone Asia/Kolkata.
Hot climate makes pre-cooling meaningful. Location is a config value (team may change it).

**PV:** `P_pv[t] = kWp × GHI[t]/1000 × derate` (derate placeholder 0.8). Optional: pvlib.

**Base load:** non-flexible building demand. Default: documented synthetic daily profile
with weekday/weekend shape + noise (seeded). Optional upgrade: a real dataset (e.g. CityLearn 2023).

**Battery:** `SoC[t+1] = SoC[t] + η_c·Pc[t]·Δt − Pd[t]·Δt/η_d`;
`SoC_min ≤ SoC ≤ SoC_max`; `0 ≤ Pc ≤ Pc_max·u[t]`, `0 ≤ Pd ≤ Pd_max·(1−u[t])`, u binary.

**EV:** present between arrival and departure; continuous charging `0 ≤ P_ev ≤ P_ev_max`
when present, 0 otherwise; `Σ P_ev·Δt ≥ E_required` by departure. (The original used binary
7.4 kW; continuous charging is a documented change.)

**Thermal (pre-cooling), linear 1R1C:**
`T[t+1] = T[t] + Δt/C · ( (T_out[t] − T[t])/R + Q_gain[t] − COP·P_cool[t] )`,
`0 ≤ P_cool ≤ P_cool_max`; comfort band `T_min ≤ T ≤ T_max` in occupied slots (soft
constraint with a large penalty on slack, so infeasible days still solve and report slack).
`Q_gain` from solar radiation and occupancy (placeholder coefficients).
The original repo's `calculate_heating_requirement` RC code may be adapted; cite it in DECISIONS.md.

**Power balance:** `G_imp − G_exp = Base + P_ev + P_cool + Pc − Pd − P_pv`;
`0 ≤ G_imp ≤ G_imp_max` (grid import limit — the coupling constraint), `G_exp ≥ 0`.

**Objective (configurable weights):** minimise `Σ price·G_imp·Δt − feed_in·G_exp·Δt`
`+ w_peak·max(G_imp) + w_comfort·Σ slack + w_deg·Σ(Pc+Pd)·Δt`.

**Prices:** pluggable source — (a) the repo's sample/ENTSO-E prices, (b) a configurable
time-of-use tariff (placeholder values, labelled as such), (c) CSV import (e.g. Indian Energy
Exchange day-ahead 15-min prices downloaded manually). Default: (b) until the team decides.

---

## 5. Evaluation protocol

**Rolling day-ahead:** for each test day d, the forecaster only sees data up to the end of
d−1; the system plans day d; `sim/simulate.py` executes the plan against ACTUAL PV, load and
weather: EV and cooling run as planned, battery runs as planned but clipped to feasibility,
the grid absorbs the difference; then metrics are computed. The oracle plans on actuals.

**Systems compared**

| ID | System | Purpose |
|---|---|---|
| S0 | Original repo, price-only, 3 appliances | Reproduce the paper (baseline sanity) |
| S1 | Rule-based (EV charges on arrival, battery charges when PV surplus, AC on thermostat) | Lower bound |
| S2 | Forecast + MILP, no LLM | Isolates what the LLM adds |
| S3 | Pure-LLM extended (LLM schedules all loads itself with forecasts) | Shows the failure mode |
| S4 | Ours: forecast + agents + solver + verifier | Proposed |
| S5 | Oracle: MILP on actual data | Upper bound |

S3 and S4 each run with a large model (e.g. Llama-3.3-70B via an API) and a small model
(≈8B via API or Ollama).

**Scenarios:** 30–60 normal days (test months, chronological split) plus conflict cases:
cloudy day, heatwave evening, tight EV deadline, cheapest hours after EV departure,
grid-limit stress (all loads want the same hours).

**Requests:** templated natural-language requests with ground-truth constraints, including
paraphrases and indirect phrasing ("I'm leaving an hour earlier tomorrow"). Used for RQ3.

**Metrics:** daily cost; peak grid import (kW); PV self-consumption (%); comfort violation
(degree-hours outside band); EV unmet energy (kWh); constraint-violation rate (% of days);
constraint-extraction accuracy (RQ3); tokens, LLM calls, latency per day; for forecasting:
MAE/RMSE/nMAE plus decision regret = cost(system) − cost(oracle).

---

## 6. LLM access
One OpenAI-compatible client (`b2g/agents/llm_client.py`) configured by `.env`:
`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`. Works with Cerebras, Groq, OpenRouter and a local
Ollama server (`http://localhost:11434/v1`). Temperature 0. Retries with backoff on rate limits.
Response cache keyed by hash(model, messages). Budget: print estimated calls before any
experiment sweep and ask for confirmation if > 500 calls.

---

## 7. Milestones (tick when done)

Phase 1 presentation needs only M0 (a screenshot of the original running). M1–M9 are Phase 2.

- [x] **M0 — Setup and reproduce.** Venv, install, `.env` from example. Make `ENTSOE_API_KEY`
  optional in `config.py` (fall back to sample prices). Run "Schedule all flexible loads for
  minimal cost". *Done when:* the original produces a schedule and it matches
  `milp-baseline/optimizer.py` for the same prices.
- [x] **M1 — Provider-agnostic LLM + headless runner.** `b2g/agents/llm_client.py`; patch the
  original orchestrator to use it (minimal change); `b2g/cli.py` runs S0 without the dashboard
  and logs JSON. *Done when:* the same S0 task runs on two different providers.
- [x] **M2 — Data pipeline.** Weather + GHI for the site (Open-Meteo archive; also try the
  Open-Meteo historical-forecast data so forecast errors are realistic — verify availability),
  PV series, base-load profile, prices. At least 12 months. *Done when:* processed files exist
  in `data/b2g/` and a sanity plot per series is saved to `results/figures/`.
- [x] **M3 — Forecaster.** Persistence baseline, LightGBM (features: forecast weather, hour,
  day-of-year, lags), optional Chronos-Bolt-small zero-shot on CPU. Chronological
  train/val/test split. *Done when:* a metrics table (MAE/RMSE/nMAE per model, PV and load)
  is saved and LightGBM beats persistence.
- [x] **M4 — Physical models.** battery, EV, thermal, site balance + unit tests (energy
  conservation, bounds, thermal drift with AC off). *Done when:* `pytest -q` passes.
- [x] **M5 — Solver, simulator, S1, S2, S5.** Joint MILP, settlement simulator, rule-based and
  oracle baselines. *Done when:* tests pass; on 7 test days the oracle has zero violations and
  cost ≤ S2 ≤ S1 on average (report if not, with explanation).
- [x] **M6 — Agents (S4 without verifier).** Prompts for orchestrator, EV, battery, pre-cooling
  agents; pydantic constraint schemas; new actions. *Done when:* one end-to-end day runs from a
  natural-language request to a solver schedule with a readable reasoning trace.
- [x] **M7 — Verifier and replanning.** Deterministic checks (SoC bounds, comfort band, EV
  energy by departure, grid limit, and request consistency: constraints match the parsed request),
  violation report back to the orchestrator, max 3 replans. Also implement S3 (pure-LLM).
  *Done when:* injected faulty constraints are caught and repaired in tests.
- [x] **M8 — Demo app** (replaces the former M8 experiment sweep and M9; scope reduced on 2026-10-25:
  the project is shown to the professor in one session). One Streamlit app (`streamlit run app.py`)
  with 4 tabs: the problem (solar vs demand), "Ask the house" (request → agents → verified schedule,
  live or from pre-run examples), smart vs simple (S1 / S4 / S5, plus the S3 pure-LLM failure), and
  results (M3 forecast and M5 baseline tables). Example requests are pre-run
  (`python -m b2g.demo.precompute`) so the demo works instantly and offline.
  *Done when:* the app opens and every tab works from the pre-run examples; tests pass.

---

## 8. Known risks
- Rate limits / free-tier quotas → caching, small day counts first, Ollama fallback.
- MILP too slow with binaries → relax battery binary (allow LP) and document it.
- Hybrid verifier rarely fails when the solver is correct → that is expected; its value shows
  on S3 and on request-consistency errors. Report both.
- Thermal parameters are synthetic → state this clearly as a limitation; keep them in config.
