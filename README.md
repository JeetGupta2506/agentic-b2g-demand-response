# Smart Home Energy Planner — Surat

**Forecast-aware hybrid agentic AI for Building-to-Grid (B2G) demand response**

B.Tech AI research project, SVNIT Surat.
Repository: https://github.com/JeetGupta2506/agentic-b2g-demand-response

A person types a request in plain English, for example *“I’m leaving at 7 tomorrow, I need the car at 90%, keep the room under 26 °C.”*
The system plans the next day of a solar-powered house in 15-minute steps: when to charge the electric car, when to charge or use the home battery, and when to pre-cool with the AC. It aims to use as little grid electricity as possible, use the house’s own solar, keep people comfortable and stay under the 8 kW grid connection limit.

**The design in one line:** LLM agents *understand* the request and set the rules, a MILP optimizer *computes* the schedule, and a verifier *checks* it and sends it back for replanning when something is wrong.

## Team

| Name | Roll number |
|---|---|
| Jeet Gupta | [roll number] |
| [Member 2] | [roll number] |
| [Member 3] | [roll number] |

Guide: [faculty name] · Course: [course name]

## Results at a glance

Plans are made on the day-ahead **forecast** and scored on the **actual** weather of that day.

| | |
|---|---|
| Electricity vs a simple rule-based house (4 example days) | **33–46% less** |
| Gap to a planner with perfect knowledge of the weather | **within about 5%** on electricity |
| Grid limit | never exceeded (simple rules hit 8 kW on every example day) |
| A pure-LLM planner on the same request | **51** physical rules broken, car 20 kWh short, room 30.2 °C |

Full explanation for newcomers: [docs/B2G_Project_Explained.pdf](docs/B2G_Project_Explained.pdf).

## How it works

```
1 Forecast  →  2 LLM agents  →  3 Optimizer  →  4 Verifier  →  5 Score
 LightGBM       orchestrator +     MILP (PuLP +     physics, wishes,    replay the plan on
 solar and      EV, battery and    CBC), 96 slots   request, answer     the actual weather
 demand         pre-cooling agents of 15 min            │ fails → replan (max 3)
```

| System | What it is |
|---|---|
| S0 | The base paper’s original system, kept runnable as the baseline |
| S1 | Simple rules: charge the car on arrival, thermostat AC, battery stores spare solar |
| S2 | Forecast + optimizer, no LLM |
| S3 | Pure LLM: the LLM writes the whole schedule itself |
| **S4** | **Our system: agents + optimizer + verifier** |
| S5 | Optimizer with perfect knowledge of the real weather (upper bound) |

## Based on

El Makroum, Zwickl-Bernhard, Kranzl (2025). *Agentic AI Home Energy Management System: A Large Language Model Framework for Residential Load Scheduling.* [arXiv:2510.26603](https://arxiv.org/abs/2510.26603).
Original code: https://github.com/RedaElMakroum/agentic-ai-hems (MIT licence). This repository is a fork of it; the original README is kept in [docs/ORIGINAL_README.md](docs/ORIGINAL_README.md).

What we added: solar and weather forecasting for Surat, a home battery and AC pre-cooling next to the EV, joint planning under a grid limit with a MILP solver, a deterministic verifier with replanning, evaluation on actual weather, and a demo website. All new code is in [`b2g/`](b2g/); the original files only received the fixes needed to run them (any LLM provider, optional ENTSO-E key).

## Dataset and resources

| Resource | Used for | Link |
|---|---|---|
| Open-Meteo Historical Weather API (ERA5 reanalysis) | “Actual” sunlight, temperature and cloud cover for Surat (21.17° N, 72.83° E), 1 Feb 2024 – 30 Sep 2026 (973 days) | https://open-meteo.com/en/docs/historical-weather-api |
| Open-Meteo Previous Runs API | Day-ahead weather forecasts (issued about one day before) | https://open-meteo.com/en/docs/previous-runs-api |
| ERA5 (ECMWF) | The reanalysis behind the actual weather | https://www.ecmwf.int/en/forecasts/dataset/ecmwf-reanalysis-v5 |
| Groq (free tier) | LLM used in our runs: `qwen/qwen3.8-27b`, temperature 0 | https://console.groq.com |
| OpenRouter (optional) | Alternative LLM provider | https://openrouter.ai |
| ENTSO-E Transparency Platform (optional) | Austrian prices for the original S0 system; without a key it uses `data/prices_sample.json` | https://transparency.entsoe.eu |

Generated, not downloaded:

- **Solar power** from sunlight: `5 kW × sunlight / 1000 × 0.8`.
- **House base load**: a synthetic daily profile (about 10 kWh on weekdays, 12 kWh on weekends) with seeded noise; no smart-meter data was available.
- **Tariff**: a placeholder Indian-style time-of-day tariff (₹7.0, ₹5.6 from 09:00 to 17:00, ₹8.4 from 18:00 to 22:00).

All device sizes, the tariff and the thermal model are **placeholders** in [`b2g/config/default.yaml`](b2g/config/default.yaml). The processed data files are not stored in the repository; `python -m b2g.data.build` downloads and rebuilds them (no API key needed).

## Implementation environment

| | |
|---|---|
| OS | Windows 11 (also runs on Linux/macOS) |
| Python | 3.11 (tested with 3.11.6) |
| Node.js | 18 or newer, only to rebuild the website (tested with 24.12) |
| Hardware | Laptop CPU only, no GPU needed |
| Main libraries | pandas, numpy, LightGBM, PuLP (bundles the CBC solver), pydantic, Flask, Streamlit, pytest; website: Next.js 14, TypeScript, Tailwind, Recharts |
| LLM | Any OpenAI-compatible API; we used Groq’s free tier |

### Setup

```bash
git clone https://github.com/JeetGupta2506/agentic-b2g-demand-response.git
cd agentic-b2g-demand-response

# Python 3.11 virtual environment (Windows)
py -3.11 -m venv .venv
.venv\Scripts\activate
# (Linux/macOS: python3.11 -m venv .venv && source .venv/bin/activate)

pip install -r requirements.txt -r requirements-api.txt -r requirements-b2g.txt

# API keys: copy the template and fill in your own key (never commit .env)
copy .env.example .env        # Linux/macOS: cp .env.example .env
#   LLM_PROVIDER=groq
#   GROQ_API_KEY=...
#   GROQ_MODEL=qwen/qwen3.8-27b
```

On Windows, run Python in UTF-8 mode for the original S0 system (`set PYTHONUTF8=1`); the `b2g` commands switch to it on their own.

### Build the data and forecasts

```bash
python -m b2g.data.build             # downloads Open-Meteo weather, builds data/b2g/processed/site_15min.csv
python -m b2g.forecasting.train      # trains and scores the forecasters (~25 s) -> forecasts.csv
```

### Run

```bash
# The demo website with live requests (open http://localhost:3000)
cd web && npm install && npm run build && cd ..     # once, builds web/out
python -m b2g.demo.server

# Our system (S4) on one request from the command line
python -m b2g.cli --system S4 --date 2026-05-06 --request "Tomorrow I'm leaving at 7 and need the car at 90%."

# Pure-LLM comparison (S3), and the week of baselines without an LLM (S1, S2, S5)
python -m b2g.cli --system S3
python -m b2g.eval.compare_baselines

# Pre-run the four demo examples (uses the LLM once; answers are cached)
python -m b2g.demo.precompute

# Older Streamlit version of the demo
streamlit run app.py

# The original paper's system (S0)
python orchestrator_agent_react.py "Schedule all flexible loads for minimal cost"
```

### Tests

```bash
pytest -q
```

139 automated tests cover the physical models, the solver, the agents (with a scripted fake LLM, no API calls), the verifier, the demo server and the app.

## Reproducibility

- Fixed random seeds, and the LLM at temperature 0.
- Every LLM call (prompt, answer, tokens, time) is logged in `results/runs/`.
- Answers are cached by prompt hash in `results/cache/`, so re-running an experiment costs no tokens.
- Forecasters are trained up to June 2025, tuned on July–December 2025 and scored on January–September 2026; all example days are in the test period.

## Repository layout

| Path | Contents |
|---|---|
| `b2g/config/default.yaml` | All placeholder numbers: devices, tariff, comfort band, solver weights |
| `b2g/data/` | Weather download, solar and base-load profiles, the 15-minute dataset |
| `b2g/forecasting/` | Persistence, weather-physics and LightGBM forecasters |
| `b2g/models/` | Battery, car, room temperature (1R1C) and site power balance |
| `b2g/solver/milp.py` | The MILP optimizer |
| `b2g/sim/` | One day’s data and the settlement on actual weather |
| `b2g/baselines/` | S1 simple rules, S2 forecast + optimizer, S3 pure LLM |
| `b2g/agents/` | LLM client, orchestrator, agent prompts and rule schemas |
| `b2g/verifier/` | The four groups of checks |
| `b2g/demo/` | Pre-run examples, web data export, the live server |
| `web/` | The Next.js demo website |
| `tests/` | pytest suite |
| `docs/` | Project plan, design decisions, explainer PDF |
| `results/` | Metrics tables, figures, demo results |

## Limitations

- Device sizes, tariff and the house’s thermal model are placeholders, not measurements.
- The house base load is synthetic; the “actual” weather is ERA5 reanalysis, not a rooftop meter.
- Results come from one week and four example days with one LLM: a demonstration, not a large study.

## Licence

MIT, as the original project. See [LICENSE](LICENSE) (copyright of the original code: Reda El Makroum, 2025).
