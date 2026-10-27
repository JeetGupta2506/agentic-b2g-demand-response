# Prompt for Claude Design: Next.js frontend for the B2G smart-home demo

> Attach the three files from `results/web_data/` (`site.json`, `examples.json`, `results.json`) together with this prompt.

---

## What I need

Design and build a **Next.js web app** that presents our B.Tech research project to a professor in a
**single live demo (about 10 minutes, on a laptop connected to a projector)**. It must look polished
and modern, and explain the idea to someone who has not read the code. It replaces a basic Streamlit page.

**Tech:**
- Next.js (App Router) with TypeScript and Tailwind CSS.
- Charts with Recharts, or another light React chart library.
- **Static only.** All data comes from the three attached JSON files, placed in `public/data/` and loaded
  with `fetch("/data/…json")` or imported at build time.
- No backend, no API calls, no login, no database. It must work **offline** (`npm run build && npm start`,
  or `next export`).
- Do not invent any numbers; every value shown must come from the JSON files.

## The project, in plain words

Title: **"Smart Home Energy Planner — Surat"**.
Subtitle: *Forecast-aware hybrid agentic AI for Building-to-Grid demand response.*

- **The problem:** a house in Surat (India) has rooftop solar, a home battery, an electric car and an
  air conditioner. The sun peaks at noon, when nobody is home, but people need power in the evening.
  Monsoon clouds make solar drop suddenly, and the weather forecasts miss some of it.
- **Our system (called S4) works in five steps.** Show these as a visual pipeline:
  1. **Forecast:** a LightGBM model predicts tomorrow's solar and house demand from weather forecasts.
  2. **LLM agents:** the person types a plain-English request (e.g. *"I'm leaving at 7 tomorrow, car at 90%,
     working from home from 2 pm, keep it under 26 °C"*). An orchestrator agent and three specialist agents
     (EV, battery, pre-cooling) turn it into precise rules.
  3. **Optimizer:** a MILP solver computes the cheapest 24-hour schedule (15-minute steps) for car
     charging, battery and AC within the 8 kW grid limit.
  4. **Verifier:** deterministic code checks the physics, the person's wishes and that the AI's explanation
     only states true numbers. If a check fails, it sends the plan back for replanning.
  5. **Score on reality:** the plan is replayed on the *real* weather of that day and compared with other systems.
- **The systems compared:**
  - **S1, simple rules:** charge the car when it is home, AC on a thermostat.
  - **S4, our system.**
  - **S5, perfect knowledge:** the optimizer with the real weather known in advance. This is the best
    possible result and cannot be achieved in practice.
  - **S3, pure LLM:** the LLM writes the whole schedule itself, with no optimizer and no verifier.
- **Key messages to land:**
  - S4 costs a third to almost half less electricity than simple rules (33–46% across the 4 examples) and
    gets within ~5% of perfect knowledge.
  - S4 keeps the house more comfortable than simple rules.
  - S3 (pure LLM) broke 51 physical rules, left the car 20 kWh short and let the room reach 30 °C. Its bill
    looks cheap only because it did not do the job.
  - So the right design is that the **LLM understands the request, the optimizer does the maths, and the
    verifier checks the result.**
- Based on: El Makroum et al. (2025), *Agentic AI Home Energy Management System*, arXiv:2510.26603.
  We extend their open-source system.

## Pages / sections

A single page with a sticky top nav (or 4 routes), in this order:

1. **Hero + "How it works":**
   - The title, a one-line pitch, and the 5-step pipeline as an illustrated flow (icons, arrows).
   - A small "the house" card: 5 kW solar, 10 kWh battery, 40 kWh car with a 7.4 kW charger, 1.6 kW AC,
     8 kW grid limit. Read these from `site.json → house`.
2. **The problem:**
   - Four headline stats from `site.json → headline`: solar kWh/day, base demand kWh/day, day-ahead
     forecast error %, days of real weather data.
   - Chart A, "Solar arrives at the wrong time": the average day, solar vs house demand over 24 h, from
     `average_day`. It can also show the price per kWh as a thin line or band on a second chart, but
     never on a dual axis.
   - Chart B, "…and varies day to day": daily solar, actual vs the forecast made the day before, from
     `daily_solar`, about 970 days. Highlight the monsoon months (June–September).
   - A callout: *"The idea: shift flexible loads to good hours: charge the car and battery from solar,
     pre-cool the house while nobody is home."*
3. **Ask the house.** This is the centrepiece. It uses `examples.json`, an array of 4 pre-run examples.
   - **Example picker:** 4 cards or tabs showing `title`, `weekday`, `date`.
   - **The request** as a chat bubble from the user, with a "playback" feel: the agent steps from `trace`
     appear one by one when you press "Run" (an animation only; the data is pre-computed). Each step has
     `action` (GET_FORECAST, GET_CALENDAR, CALL_AGENT with `agent`, RUN_SOLVER, VERIFY, FINISH), a
     `thought`, and either `agent_answer` (JSON of the rules that agent set) or `observation`
     (a JSON string).
   - **"What the AI understood":** the `constraints` object as friendly chips. Map the field names to labels:
     - `ev.departure_time` → "🚗 Car leaves at"; `ev.arrival_time` → "Car back at";
       `ev.target_soc` → "Car charge needed" (show as %); `ev.max_power_kw`; `ev.skip_charging`.
     - `battery.reserve_soc` → "Battery backup reserve" (%);
       `battery.allow_grid_charging: false` → "Battery charges only from solar".
     - `precool.comfort_max_c` → "Max room temperature"; `precool.comfort_min_c`;
       `precool.away_from` / `away_until` → "House empty from / someone home again at";
       `precool.home_all_day` → "Someone home all day".
     - An empty section means "usual routine".
   - **Four outcome cards:**
     - Car at departure (`plan_summary.ev.kwh_at_departure` / `target_kwh`, green if `target_met`).
       If `departure` is "no trip", show "no trip".
     - Warmest while home (`plan_summary.room.max_temp_when_home_c` vs the wish `comfort_band_c[1]`;
       amber if above).
     - Electricity on the real day (`comparison["S4 our system"].electricity_cost`, ₹).
     - Verifier (`verification.passed`, number of `warnings_to_tell_the_person`).
   - **The AI's answer:** `answer` (markdown with emojis) in a nice message card, a "✓ verified" badge, and
     the warnings shown honestly. Replace `degC` with °C in any text.
   - **Charts of the day** from `series`. Each array has 96 values (15-min slots; hour = index × 0.25)
     except `temps`, `e_bat` and `e_ev`, which have 97 values (state at each slot boundary).
     - **Power:** a stacked step-area of `base`, `ac`, `ev` and `charge` (kW), with `pv` (solar) as a bold
       line on top. The grid limit `import_limit_kw` can be a dashed reference line.
     - **Room temperature:** `temps` vs outdoor `t_out`, with the comfort band `comfort` = [min, max] shaded.
       Shade the periods where `occupied` is false (nobody home) in light grey.
     - **Stored energy:** `e_bat` (home battery, kWh) and `e_ev` (car, kWh).
4. **Smart vs simple:**
   - Use the same example picker (or a shared selection). For the chosen example, show `comparison` (keys:
     "S1 simple rules", "S4 our system", "S5 perfect knowledge", and "S3 pure LLM" for the first example only)
     as a table or cards: electricity ₹ (`electricity_cost`), total ₹ including penalties (`total_cost`),
     discomfort °C·h (`comfort_dh`), car short kWh (`ev_unmet_kwh`), peak grid kW (`peak_import_kw`),
     solar self-use % (`self_consumption_pct`) and `violations`.
   - Two simple bar charts: electricity ₹ and discomfort °C·h, one bar per system. Use a fixed colour per
     system everywhere: S1 grey, S4 brand blue, S5 green, S3 red.
   - **The S3 story** (only when the example has an `s3` block):
     - a red/warning panel "Why not let the LLM do the maths itself?";
     - `s3.errors` (number of physical rules broken), the first 3 of `s3.error_examples`, `s3.warnings`
       (wishes it missed), and a quote of its own `s3.reasoning` (truncated);
     - the punchline: "its reasoning said one thing, its schedule did another".
5. **Results:**
   - **Forecast accuracy table:** `results.json → forecast_accuracy_test` (target, model, nMAE %; lower is
     better). Show it as a grouped bar chart or a clean table.
   - **Forecast error by month:** a line chart from `forecast_error_by_month` (`month`, plus series per model
     for `pv` and for `load`). Mark the boundary between validation and test (`validation_test_split.val_end`,
     2025-12-31). Note that the monsoon months are the hard ones.
   - **One-week comparison** (`week_comparison`, 4–10 May 2026, daily averages): systems "S1 rules",
     "S2 MILP (pv=lgbm)", "S2 MILP (pv=physics)" and "S5 oracle" (S2 = forecast + optimizer, no LLM).
   - **Honest limitations** (keep this, the professor will like it):
     - device sizes, tariff and the house heat model are placeholders;
     - the house base demand is synthetic, and the "actual" weather is ERA5 reanalysis, not a rooftop meter;
     - the results come from a few example days and one LLM (Qwen 3.8 27B on Groq's free tier), not a large study.
6. **Footer:** team (3 B.Tech students, SVNIT Surat), the base paper citation, and "Built on the open-source
   agentic-ai-hems (MIT)".

## Design direction

- **Look:** clean, modern, "energy-tech" feel. Light theme by default; a dark mode is nice but optional.
  - Lots of white space, large readable numbers (it will be on a projector, so use big type and high contrast).
  - Rounded cards and subtle motion (staggered reveal of the agent steps, count-up numbers). Nothing flashy.
- **Colour meanings, used consistently everywhere:**
  - solar = warm yellow/amber;
  - house demand / base load = blue;
  - AC = orange;
  - car = green/teal;
  - home battery = gold.
  Use the system colours above. Avoid red except for S3 and errors.
- **Charts:** a 24-hour x-axis with ticks every 3 h, units on the axes (kW, kWh, °C, ₹), tooltips, and
  legends on top. No dual y-axes. No 3D or pie charts.
- **Layout:** desktop-first (1440 px projector) but also fine on a phone. Nothing should need horizontal
  scrolling except wide tables.
- **Copy:** short and plain English; the professor is the audience, not engineers. Use ₹ for money.

## Data files (shapes)

```ts
// site.json
{ house: { city, pv_kwp, battery_kwh, ev_kwh, ev_charger_kw, ac_kw, grid_limit_kw, comfort_c: [min,max],
           weekday_away: ["08:00","18:00"], data_range: [start,end] },
  headline: { solar_kwh_per_day, base_demand_kwh_per_day, forecast_error_pct, days_of_data },
  average_day: { solar_kw: number[96], demand_kw: number[96], price_inr_per_kwh: number[96] },
  daily_solar: { date: string[], actual_kwh: number[], forecast_kwh: number[] } }

// examples.json: Example[] (4 items; the first one also has "S3 pure LLM" + s3)
{ title, date, weekday, request, ok, error,
  constraints: { ev: {...}, battery: {...}, precool: {...} },      // only the fields the request changed
  agent_reasoning: { ev, battery, precool },                        // one sentence each
  answer: string,                                                   // markdown
  plan_summary: { estimated_electricity_cost,
    ev: { departure, target_kwh, kwh_at_departure, target_met, charging },
    room: { comfort_band_c, someone_home, ac_on, max_temp_when_home_c, planned_discomfort_degC_h },
    home_battery: { reserve_kwh, lowest_planned_kwh, charging, charged_from, discharging },
    grid: { peak_import_kw, limit_kw } },
  verification: { passed, errors: string[], warnings_to_tell_the_person: string[] },
  replans: number, explanation_fixed: boolean,
  trace: { step, action, params, thought, observation, agent?, agent_answer? }[],
  series: { pv, base, ev, ac, charge, discharge, grid_import, grid_export, price, t_out: number[96],
            temps, e_bat, e_ev: number[97], occupied: boolean[96], comfort: [min,max],
            import_limit_kw, battery_min_kwh, ev_target_kwh },
  comparison: { [system: string]: { electricity_cost, total_cost, comfort_dh, ev_unmet_kwh, peak_import_kw,
                self_consumption_pct, import_kwh, ac_kwh, violation, violations: string[] } },
  s3?: { format_ok, errors: number, error_examples: string[], warnings: string[], reasoning: string } }

// results.json
{ forecast_accuracy_test: { target, model, nmae_pct }[],
  forecast_error_by_month: { month: string[], pv: { [model]: number[] }, load: { [model]: number[] } },
  validation_test_split: { train_end, val_end, test_end },
  week_comparison: { dates: [start,end], rows: { system, total_inr, electricity_inr, discomfort_degc_h,
                     peak_kw, solar_used_pct }[] } }
```

## Out of scope

- Typing a new request live. That needs the Python backend and an LLM key; the Python/Streamlit app still
  does it. At most, show a disabled input with the note "Live mode runs in the Python app".
- Authentication, analytics, CMS, i18n.
