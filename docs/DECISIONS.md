# Design Decisions

One entry per decision: date, decision, why. Newest at the bottom.

---

## 2026-10-22 — M0: ENTSO-E key is optional
**Decision:** `config.py` prints a warning instead of raising when `ENTSOE_API_KEY` is missing.
`.env.example` now has the ENTSO-E line commented out.
**Why:** `tools.get_electricity_prices` already falls back to `data/prices_sample.json`, so the
hard error only blocked setup. A placeholder key in `.env` would also trigger a failing API call
before the fallback.

## 2026-10-22 — M0: missing dependencies added in `requirements-b2g.txt`
**Decision:** Added `python-dotenv` (imported by `config.py`) and `numpy` (imported by
`milp-baseline/optimizer.py`), plus `pytest`. The original `requirements.txt` is unchanged.
**Why:** A clean install of the original requirements cannot import either file.

## 2026-10-22 — M0: reproduce by comparing start slots, not euros
**Decision:** The M0 check compares the LLM run's start slot per appliance with
`milp-baseline/optimizer.py`. Expected on the reference prices with the EV ready by 07:00:
washing machine slot 10 (02:30), dishwasher slot 11 (02:45), EV slot 1 (00:15).
**Why:** `optimizer.py` computes `cost_eur` with 1.8 kW for every appliance, so its euro figure is
only right for the dishwasher. The slot is the decision; the cost follows from it. With no ENTSO-E
key the agents use `data/prices_sample.json`, which is identical to `test_prices_reference.json`
(checked in a test), so both solve the same problem.

## 2026-10-22 — M0: `.gitignore` exceptions for our tests and results
**Decision:** Added `!tests/test_*.py`, `!results/*.csv`, ignored `results/runs/` and `.venv/`.
**Why:** The original ignores every `test_*.py` and `*.csv`, which would silently drop our pytest
suite and `results/summary.csv` from git.

## 2026-10-22 — M0: LLM provider configurable (pulled forward from M1), Groq for now
**Decision:** The hard-coded Cerebras URL (4 places in `orchestrator_agent_react.py` and `tools.py`)
now comes from `LLM_API_BASE` in `.env` (default `https://api.cerebras.ai`, so the original setup
still works). The key may be given as `LLM_API_KEY`. All four calls go through
`tools.post_chat_completion`, which retries HTTP 429 up to 6 times (Groq free tier: 7000 input
tokens/min for qwen3.8-27b, one agent call ≈ 3800; 3 retries was not enough) using the provider's
`Retry-After`, and also retries HTTP 500/502/503 (Groq returned "model over capacity" once) and
connection errors/timeouts (a short Wi-Fi drop killed one run). We use Groq's free tier because Cerebras now asks for a payment method.
**Why:** Without this the original cannot run on any free provider. Groq's free tier rate-limited
about 10 of the calls in one run; without the retry the run would have crashed.
The full provider-agnostic client is still M1.
**Limit found:** Groq free tier allows 200,000 tokens/day per model (refills ~8k/hour). One full
S0 run uses roughly 100–150k tokens (the specialist agents receive all 96 prices plus tool rounds),
so only about one full run per model per day. Not enough for M8 sweeps; revisit in M1/M8
(response cache, other providers, local Ollama).
**Note:** Groq no longer offers Llama-3.3-70B (checked 2026-10-22). Available paper model:
`openai/gpt-oss-120b`. On Windows, run with `PYTHONUTF8=1`, else the original's ✓/⚠ prints crash
when output is piped (e.g. by the dashboard's `api.py`).

## 2026-10-22 — M0: dashboard API runs on Windows
**Decision:** `api.py` loads `.env`; on Windows (`os.name == 'nt'`) it starts the orchestrator with
its own Python (`sys.executable`) instead of `bash -c "python ..."`, and sets `PYTHONUTF8=1` /
UTF-8 decoding for the child process. Mac/Linux keep the original command.
**Why:** On Windows `bash` is WSL (no venv, no packages), the original never read `.env` so the
model list was empty, and the ✓/⚠ output crashed on cp1252 pipes.

## 2026-10-22 — M0 result: S0 reproduced with `qwen/qwen3.8-27b` (Groq)
**Decision:** Use `qwen/qwen3.8-27b` as the working model for S0 until M1.
**Result:** "Schedule all flexible loads for minimal cost" on the reference prices →
washing machine slot 10, dishwasher slot 11, EV slot 1, identical to `milp-baseline/optimizer.py`
(`tests/test_m0_reproduce.py`, 4 passed). 9 iterations, 34,883 orchestrator tokens, 34 s.
`openai/gpt-oss-120b` (one of the paper's models) scheduled only 2 of 3: in one reply it invented
the EV agent call, its answer and the schedule confirmation, then claimed all three were done.
This matches the paper's 0/5 for GPT-OSS-120B on all three appliances.
**Why:** It matches the optimizer; the paper's Llama-3.3-70B is no longer on Groq. Note the run
is a single sample, not the paper's 5 repetitions; the larger evaluation is M8.

## 2026-10-24 — M1: one LLM client (`b2g/agents/llm_client.py`) for all calls
**Decision:** All 4 LLM call sites of the original (orchestrator, 2 in the appliance agents,
calendar) call `get_client().complete(payload)`. The original still builds its own request, so
prompts and behaviour are unchanged; the client only sends, caches, retries and logs. M0's
temporary `tools.post_chat_completion` and `config.LLM_CHAT_URL` were removed. Built on `requests`
(already installed, proven in M0) rather than adding the `openai` package.
**Why:** One place for provider choice, determinism and cost control; the plan requires every LLM
call to be logged and cached.

## 2026-10-24 — M1: provider selection by name, one key per provider
**Decision:** `LLM_PROVIDER=cerebras|groq|openrouter|ollama` picks a preset URL; each provider reads
`<PROVIDER>_API_KEY` and `<PROVIDER>_MODEL`, so several keys can sit in `.env` and
`python -m b2g.cli --provider X` switches for one run. `LLM_BASE_URL` covers any other
OpenAI-compatible server. M0 names (`LLM_API_BASE`, `LLM_API_KEY`, `CEREBRAS_MODEL`) still work.
Nothing set → Cerebras + llama-3.1-8b, the original defaults. `api.py`'s model list uses the same
resolution.
**Why:** Switching provider must not mean editing keys; the base paper's setup stays reproducible.

## 2026-10-24 — M1: cache key includes the provider URL; cache on by default
**Decision:** Cache key = SHA-256 of (provider base URL, full request: model, messages, tools,
temperature, max_tokens). One JSON file per answer in `results/cache/` (gitignored). Modes:
`on` (default), `off`, `refresh` (ask again, overwrite). Failed calls are never cached. Token
counters in the summary count only tokens actually spent (cache hits = 0).
**Why:** Same model name on two providers can give different answers, so a provider switch must
really ask the new provider. Measured: repeat S0 run on Groq = 15/15 calls from cache, 0 tokens,
0.2 s (vs 55,556 tokens, 25 s).
**Correction to M0:** a full S0 run costs ~56k tokens (15 calls), not 100–150k; the M0 estimate
included failed and retried attempts. Groq's 200k/day therefore allows ~3 fresh runs per model.

## 2026-10-24 — M1 result: same S0 task on two providers, both match the optimizer
**Result:** "Schedule all flexible loads for minimal cost", reference prices, `python -m b2g.cli`:

| Provider | Model | Slots WM/DW/EV | Matches optimizer | Calls | Tokens | LLM time |
|---|---|---|---|---|---|---|
| Groq | `qwen/qwen3.8-27b` | 10 / 11 / 1 | yes | 15 | 55,556 | 25 s |
| OpenRouter | `nvidia/nemotron-3-ultra-550b-a55b:free` | 10 / 11 / 1 | yes | 15 | ~58,000 | ~363 s |
| either, repeated | from cache | same | yes | 15 | 0 | 0 s |

**Decision:** OpenRouter's second model is Nemotron-3-Ultra. `google/gemma-4-31b-it:free` (first
choice, similar size to Qwen 27B) was rate-limited upstream; 7 other free models were probed with a
tool call (agents need tool calling) and the largest working one was chosen.
**Limits:** OpenRouter free tier = 50 requests/day (failed requests are not counted) → 3 fresh S0
runs/day. Free models are slow (~6 min per run) and their availability changes daily.
**Fixes found by this run:** the original names its run folder after the model, and ':' (OpenRouter
`:free`) is invalid on Windows → replaced with '_' in `_save_run_data`. The CLI now writes
`summary.json` even if the orchestrator crashes.

## 2026-10-24 — M1: CLI restarts itself in Python UTF-8 mode
**Decision:** `python -m b2g.cli` re-launches with `-X utf8` when UTF-8 mode is off.
**Why:** The original opens its prompt `.md` files and prints ✓/⚠ with the default encoding
(cp1252 on Windows) and crashes; this removes the need for `PYTHONUTF8=1` when using the CLI.

## 2026-10-24 — M2: the building is one household (team decision)
**Decision:** `building.type: house` in `b2g/config/default.yaml`. Placeholders: 5 kWp PV,
10 kWh/day base load on weekdays, 12 on weekends, Saturday + Sunday as weekend.
**Why:** Continuity with the base paper (household, 7.4 kW EV charger) and the briefing's story
(evening demand peak after sunset). An office building remains possible by changing the config.

## 2026-10-24 — M2: weather sources — ERA5 as "actual", previous-runs day-1 as "forecast"
**Decision:** Actual weather = Open-Meteo archive API (ERA5 reanalysis). Forecast = Open-Meteo
previous-runs API, `*_previous_day1` (the forecast issued ~24 h earlier). Variables: GHI
(shortwave_radiation), temperature_2m, cloud_cover. Period 2024-02-01 .. 2026-09-30 (973 days).
**Why:** The previous-runs data are real day-ahead forecasts, so forecast errors in RQ2 are realistic
instead of synthetic noise. They start 2024-01-20 for this site (found by bisection; 2024-01-19 is
incomplete), so the period starts 1 Feb 2024.
**Checked for Surat:** archive and previous-runs are hourly only (no native 15-min);
historical-forecast has 15-min but stitches each run's first hours (near-analysis, not day-ahead).
**Limitations:** ERA5 is a reanalysis (a weather model's reconstruction), not ground measurements.
Forecast and "actual" come from different models, so part of the error is model disagreement.
Measured: daily irradiation nMAE 9.6 %, bias −0.26 kWh/m² per day (forecast lower), temperature
MAE 0.9 °C; errors are largest in the monsoon.

## 2026-10-24 — M2: hourly → 15-min conversion
**Decision:** Radiation (hourly means, labelled with the END of the hour) is placed at hour midpoints,
linearly interpolated to slot midpoints, clipped at 0, and rescaled so each hour's 4 slots keep that
hour's mean exactly (energy-preserving, tested). Temperature and cloud cover (instantaneous) are
interpolated to slot midpoints. A missing hourly value makes the touching slots missing, and any
day with a missing slot is dropped and listed in `site_15min_meta.json` (0 dropped in the build).
**Why:** A flat step per hour makes sunrise/sunset unrealistically blocky for 15-min scheduling,
while energy per hour must not change (it is what PV and cost depend on).

## 2026-10-24 — M2: base load and tariff placeholders
**Decision:** Base load = daily kWh × hourly shape (evening peak 18–22 h) × per-slot noise
N(1, 0.15), seeded by (seed, date) so a day is identical whatever range is built. It excludes AC, EV
and battery (modelled as flexible loads later). Default price source = time-of-day tariff
(placeholder: 7.0 INR/kWh normal, 5.6 in solar hours 09–17, 8.4 in the evening peak 18–22).
Sources `sample` (repo's Austrian prices, EUR/kWh) and `csv` (e.g. IEX 15-min, Rs/MWh ÷ 1000) are
implemented and tested.
**Why:** Plan section 4 default (b). The tariff's shape (cheap solar hours, dear evening) follows the
idea of India's time-of-day tariffs, but the numbers are not a real tariff; replace them when the
team decides.

## 2026-10-24 — M2: pandas 3 time handling
**Decision:** Timestamps are converted with `as_unit("ns")` before numeric interpolation; local
naive time (Asia/Kolkata has no DST, so every day has exactly 96 slots).
**Why:** pandas 3 indexes can be stored in s/us/ns; mixing them silently broke interpolation (caught
by tests).

## 2026-10-24 — M3: split, models and protocol
**Decision:** Chronological split: train 2024-02-01..2025-06-30, validation 2025-07-01..2025-12-31,
test 2026-01-01..2026-09-30 (each part has a monsoon). LightGBM settings chosen on validation MAE
(grid of 12, early stopping); validation forecasts from a model trained on train only; test forecasts
from a model retrained once on train + validation with the chosen settings and tree count. Inputs for
day d use only actuals up to d−1, the day-ahead weather forecast for d, and the calendar (tested by
changing day d's actuals). Baselines: persistence, same-day-last-week (load), weather-forecast physics
(PV). Chronos skipped (PyTorch ~1 GB; team choice A). LightGBM via its native API (no scikit-learn).
**Why:** Plan section 5 (rolling day-ahead, no look-ahead); fixed seeds + `deterministic` for
reproducibility. nMAE = MAE / mean actual over all slots including night.

## 2026-10-24 — M3 result: LightGBM beats persistence; for PV the physics baseline wins on test
**Result (test, Jan–Sep 2026, 273 days; `results/m3_forecast_metrics.md`):**

| Target | Persistence | Same day last week | Weather physics | LightGBM |
|---|---|---|---|---|
| PV nMAE | 9.8 % | – | **7.0 %** | 8.1 % |
| Base load nMAE | 20.6 % | 16.8 % | – | **12.0 %** |

Acceptance (LightGBM beats persistence on both) is met. On **validation** (Jul–Dec 2025) LightGBM
was best for PV by far (13.9 % vs physics 18.5 %, persistence 17.5 %).
**Finding — the weather forecast's error changed over time:** the physics PV forecast's bias was
−5.2 and −5.3 kWh/day in Q3 2024 and Q3 2025 (monsoon forecasts far too low) but +0.15 in Q3 2026.
LightGBM learned the old pattern (60 % of its importance is yesterday's PV, i.e. "trust yesterday
over the forecast in the monsoon"); when the bias vanished in 2026 that correction hurt. Likely cause:
a change in the upstream weather model behind Open-Meteo's forecasts (not verified).
**Implication:** a forecaster chosen on validation is not necessarily best on later data (drift).
Both forecasts are kept in `forecasts.csv` so M5+ can measure which one gives cheaper schedules (RQ2).
Base-load results only check the method: the load is synthetic (shape + noise), so ~12 % is close to
the noise floor that no model can beat.

## 2026-10-24 — M4: physical models and their placeholder values
**Decision:** `b2g/models/` implements plan section 4 as plain simulations + checks (the MILP in M5
encodes the same equations; the simulator and verifier reuse these):
- Battery 10 kWh, 5 kW, 95 %/95 %, usable 10–100 %, start 50 %. Never charge and discharge in the
  same slot. `clip_to_feasible` nets and caps a plan slot by slot (used for settlement on actuals).
- EV 40 kWh, 7.4 kW (base paper's charger), 92 %, **continuous** charging power (documented change
  from the original's binary 7.4 kW). Weekdays: away 08:00–18:00, 80 % required at departure, 16 kWh
  trip removed on arrival; weekends at home, no deadline.
- Thermal 1R1C: R = 3 °C/kW, C = 8 kWh/°C (time constant 24 h), 1.5-ton AC (1.6 kW, COP 3.3), gains
  1.5 kW per kW/m² GHI + 0.3 kW while occupied, comfort 24–27 °C only while occupied (weekdays
  18:00–08:00, weekends all day), hard minimum 20 °C. Comfort is judged on the end-of-slot temperature
  T[t+1]. Structure follows the original `tools.calculate_heating_requirement` (heat loss = ΔT/R,
  ΔT = net heat · Δt / C), rewritten for cooling with a COP. Explicit step; stability (Δt < R·C) is
  checked when loading the config.
- Grid import limit 8 kW (EV 7.4 + AC 1.6 + base exceeds it → the loads must share); export credit
  2.5 INR/kWh. Self-consumption = (PV − export) / PV.
**Why:** Plan section 4 equations; values plausible for a Surat house, all in `default.yaml`.
**Observation (sanity figure `m4_thermal_demo.png`, hottest day 22 May 2024, 44 °C outside):** with
the AC off the room peaks at 33.6 °C; a reactive thermostat leaves 23.6 °C·h of discomfort because
one 1.5-ton AC cools this much thermal mass only ~0.6 °C/h. So on extreme days only pre-cooling
(predictive) can keep comfort — favourable for the research question, but strongly driven by R, C
and AC size, which are placeholders. Calibrate before drawing conclusions about comfort.

## 2026-10-24 — M5: day-ahead MILP formulation
**Decision:** `b2g/solver/milp.py` (PuLP + bundled CBC, 1 thread). Objective = electricity bought −
export credit + w_peak·peak + w_wear·throughput + w_comfort·degree-hours outside the band (occupied)
or below t_min + w_ev·(kWh short at departure + trip_gap). Placeholders: w_peak 1, w_wear 1.5,
w_comfort 50, w_ev 100 (INR). Comfort, t_min and the EV target are soft so every day solves and the
shortfall is reported; the grid limit and device limits are hard. Battery must end the day at least
as full as it started. If the car leaves with less than the trip needs it returns empty (`trip_gap`),
matching `models.ev.simulate` (found by a test: without it such days were infeasible). Start states
are clamped into their allowed ranges.
**Why:** Plan section 4 objective; soft constraints so infeasible days still produce a plan.

## 2026-10-24 — M5: battery binary relaxed ("auto")
**Decision:** Solve the LP relaxation first; re-solve with the charge/discharge binary only if a slot
has both > 0. **Why:** with binaries some days took 10–60 s (a 7-day, 4-system run did not finish in
10 min); the LP takes ~0.3 s. With losses (η < 1) and a positive wear cost, charging and discharging
together only adds cost, so the LP optimum avoids it (checked in tests). This is the fallback named
in plan section 8.

## 2026-10-24 — M5: systems and settlement
**Decision:** S1 = slot-by-slot rules on measured (actual) values: thermostat AC (full power while
occupied and above 27 °C), EV charges whenever home until 80 % but slows to keep import ≤ 8 kW (team
choice A), battery stores PV surplus / covers shortfall. S2 = MILP on the day-ahead forecasts, run
twice: PV from LightGBM (the validation choice) and PV from the weather-forecast physics; load from
LightGBM; outdoor temperature and GHI from the weather forecast. S5 = MILP on actual data. Every
system is settled on actual data (`sim/simulate.settle`: EV and AC as planned, battery and EV clipped
to feasibility, grid takes the rest) and carries its own actual end state to the next day. First day
starts with the battery at 50 %, the car at 40 % (back from a trip), the room at 27 °C. Systems are
compared on total cost = electricity + wear + comfort penalty + EV penalty (same weights as the
solver), with electricity cost also reported. Violation day = import above the limit or EV short.
(S2 and S5 share `baselines/forecast_milp.py` rather than a separate oracle.py.)

## 2026-10-24 — M5 result: oracle ≤ S2 ≤ S1 on 4–10 May 2026
| System | Total INR/day | Electricity | Discomfort °C·h | Peak kW | Self-consumption | Violations |
|---|---|---|---|---|---|---|
| S1 rules | 627.9 | 153.1 | 8.93 | 6.40 | 67 % | 0/7 |
| S2 (PV LightGBM) | 144.0 | 104.9 | 0.33 | 1.95 | 96 % | 0/7 |
| S2 (PV physics) | 144.3 | 104.3 | 0.33 | 1.95 | 96 % | 0/7 |
| S5 oracle | 124.9 | 101.0 | 0.01 | 1.86 | 99 % | 0/7 |

Acceptance met (oracle 0 violations; oracle ≤ both S2 ≤ S1, also on electricity cost alone). S1's
total is dominated by discomfort (the reactive thermostat cannot catch up, see M4) and it buys more
electricity because the EV charges on arrival and the AC runs in the evening peak. The optimiser
pre-cools on solar while nobody is home and runs the evening from the battery (`m5_oracle_day.png`).
The two S2 variants are nearly identical in this dry-season week (forecasts are good in May); the
RQ2 comparison needs monsoon weeks (M8). Runtime: ~12 s for 4 systems × 7 days.

## 2026-10-24 — M6: agent design (S4 without verifier)
**Decision:** New orchestrator `b2g/agents/orchestrator.py` with the original's ReAct format
(`ACTION: NAME | key=value`) and actions GET_FORECAST, GET_CALENDAR, CALL_AGENT, RUN_SOLVER, FINISH;
original files untouched (S0 still reproducible). Specialist agents (ev, battery, precool) return
JSON with only the fields the request changes (omitted = config default), validated by pydantic
(`schemas.py`: 15-min times, fractions 0–1, consistent ranges, no unknown fields); one repair attempt
with a short error message, then defaults and a warning in the trace. `apply.py` writes the
constraints into a per-day copy of the asset parameters, so the planner and the settlement on actual
data use the same rules (car times, target, charger limit, skip; battery reserve and "solar-only"
charging; comfort band and occupancy). New solver option: no grid charging → battery charge ≤
forecast PV surplus. The LLM sees compact summaries (never 96-number lists) built from the forecast
only. Parsing keeps only the first ACTION line of a reply (drops invented observations, as seen with
gpt-oss in M0) and removes `<think>` blocks. Max 12 steps; FINISH only after a solver run.
**Why:** Plan section 2 (agents set goals/constraints, solver computes); fewer free fields = fewer
ways for an LLM to be wrong; schema validation is the first safety layer before the M7 verifier.

## 2026-10-24 — M6 result: demo day end to end (Groq qwen3.8-27b)
**Request:** "Tomorrow I'm leaving at 7 instead of 8 and I need the car at 90%. I'm working from home
from 2 pm, keep it under 26 °C. Keep at least 30% in the battery in case of a power cut." (Wed 6 May 2026)
**Result:** 7 steps, 10 LLM calls, 10,474 tokens, 15 s. Constraints extracted exactly as intended:
departure 07:00, target 0.9, reserve 0.3, comfort max 26 °C, home from 14:00. Settled on the actual
day: EV met, no violations, discomfort 0.77 °C·h, electricity 187.7 INR (not comparable with M5's
S2 numbers: stricter comfort and an earlier, fuller car). Trace: `results/runs/m6_demo/trace.md`.
**Finding:** the LLM's final explanation overstated the plan twice: it said the battery charges
"from the grid" at midday (the plan only gives the time window, which is the solar window) and marked
"room at or below 26 °C while home" as met, although the solver's summary says max 26.9 °C and 0.78
°C·h planned discomfort (the 1.5-ton AC cannot hold 26 °C in the hottest hours). Constraints and
schedule were right; the report was not. → M7's verifier must also check the explanation against
the plan numbers, not only physical limits.

## 2026-10-24 — M7: verifier design
**Decision:** `b2g/verifier/checks.py`, four groups. Physics (error): battery, EV (home, charger,
capacity), AC limits, AC cooling below t_min, grid import limit, all on the plan's forecast data.
Wishes (warning, with the number the explanation must mention): EV short at departure, room outside
the comfort band while home — warnings because replanning cannot fix a physically impossible wish
(e.g. AC too small) but the person must be told. Request consistency (error, names the agent to ask):
rule-based `request_facts.py` reads explicit times ("7", "2 pm", "19:30"; a bare hour gives both
07:00 and 19:00), relative shifts ("an hour earlier"), percentages, °C, kW and a few phrases; every
fact must be used by a constraint or equal a default (not ignored) and every changed field must be
backed by a fact, a shifted default, or the documented rule comfort_min = comfort_max − 2 (not
invented). Explanation (error): every time, %, °C, kWh, kW and ₹ figure must appear in a tool
observation or the request (agent/LLM rejection messages do not count — a test caught that they
would otherwise "ground" invented numbers); each wish warning's number must be mentioned; no
"all wishes met" with warnings; the battery's source must match the new `charged_from` plan field
(charging in a slot counts as grid up to that slot's import).
**Orchestrator:** new VERIFY action; FINISH accepted only after VERIFY on the latest plan; with errors
it requires a replan (call the named agent again → RUN_SOLVER → VERIFY), max 3; then FINISH is
allowed and remaining errors are appended to the answer. Explanation: one rewrite, then an answer
generated from the verified numbers (`fallback_explanation`). `--no-verify` keeps the M6 prompt and
behaviour for the M8 ablation.
**Limitations:** the request check understands explicit numbers, not vague wishes; heuristics can
raise false alarms (bounded by the 3-replan limit, then disclosed). RQ3 accuracy is measured properly
against ground truth in M8.

## 2026-10-24 — M7: S3 pure-LLM scheduler
**Decision:** `b2g/baselines/pure_llm.py`: the LLM receives the request, device limits and models,
start state, routine and the HOURLY forecast (24 values per series) and returns hourly EV, AC and
battery kW (repeated over the four 15-min slots); one retry on bad format, else "do nothing". No
agents, solver or verifier help. Judged (verifier + settlement on actual data) under the request's
ground-truth constraints. **Why hourly:** 96 × 3 numbers per day would be an unfair amount to
generate; hourly is the more generous setting for the pure-LLM baseline.

## 2026-10-24 — M7 result: demo day, S4 with verifier vs S3 (Groq qwen3.8-27b)
| | S4 (agents + solver + verifier) | S3 (pure LLM) |
|---|---|---|
| Constraints / interpretation | exactly the demo truth | its own reasoning saw "charge 04:00–07:00", its JSON charged 07:00–17:00 |
| Verifier | passed, 1 warning (room 26.9 °C) disclosed in the answer | failed: 51 errors (45 EV charging while away / overfull, 6 grid > 8 kW) |
| Actual day: EV short / discomfort | 0 kWh / 0.77 °C·h | **20 kWh** / **30.95 °C·h** (room 30.2 °C) |
| Electricity / total cost (INR) | 187.7 / 247.1 | 85.3 / 3632.7 (cheap because it did not do the job) |
| LLM calls / tokens | 11 / 12.5k | 1 / 2.3k |

The S4 answer now states the 26.9 °C warning and "charges from solar" correctly on the first try (the
prompt rules plus the `charged_from` field prevented the M6 errors), so the live run did not need the
explanation check; it is exercised by tests (false claims → one rewrite → generated answer). Acceptance:
injected faulty constraints are caught and repaired (`test_injected_wrong_constraint_is_caught_and_repaired`).

## 2026-10-25 — M8: one Streamlit demo app instead of an experiment sweep
- **Decision:** the project goal is a one-day demo for the teacher, so the former M8 (multi-day experiment
  sweep, ablations) and M9 were replaced by a single Streamlit app (`app.py`, 4 tabs: the problem, ask the
  house, smart vs simple, results). **Why:** keep it small; every number shown already exists from M2–M7.
- **Decision:** example requests are pre-run (`python -m b2g.demo.precompute`, results in `results/demo/*.json`)
  and the app reads those files. **Why:** the demo works instantly and offline, with no risk from free-tier
  rate limits or the network. A "type my own request" mode calls the LLM live and falls back to an error
  message pointing to the pre-run examples.
- **Decision:** for each example, S1 (rules) and S5 (perfect knowledge) run under the *same* constraints the
  agents produced, and all systems are settled on the actual day. S3 (pure LLM) is run for the first example only.
- **Decision:** Streamlit + Altair (already bundled with Streamlit); no extra frontend stack. App tested with
  Streamlit's `AppTest` (every example renders in every tab without exceptions).
- **Result (4 examples, Groq qwen3.8-27b, all verified):** S4 electricity vs S1 rules: 188 vs 347, 200 vs 312,
  228 vs 339, 151 vs 276 INR, always within ~5% of S5 perfect knowledge on electricity, with less
  discomfort than S1 on every example (0.8 vs 12.2, 4.5 vs 5.0, 1.1 vs 3.2, 0.5 vs 1.0 °C·h). 37 LLM calls (12 cached), 35k tokens for the whole precompute.

## 2026-10-25 — Demo website (Next.js) with live requests
- **Decision:** the final demo front end is a static Next.js site (`web/`, generated with Claude Design from
  `docs/FRONTEND_PROMPT.md` and the JSON from `python -m b2g.demo.export_web`), not Streamlit. **Why:** better
  presentation; every number still comes from our exported files.
- **Decision:** live requests use a small Flask server (`python -m b2g.demo.server`) that serves the built site and
  one endpoint, `POST /api/plan`, running the same `run_example` as the pre-run examples. **Why:** the agents, MILP
  and verifier are Python and cannot run in the browser; Flask was already a dependency (original `api.py`), so
  one command replaces Streamlit. Live days are limited to the test period (2026-01-01..2026-09-30), one request
  at a time, results saved to `results/demo/live/` (kept apart from the pre-run examples).
- **Checked:** live request on 2026-06-10 via Groq qwen3.8-27b planned in 12 s, verified (1 warning disclosed),
  47 % cheaper than simple rules on the actual day.
