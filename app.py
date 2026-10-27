"""B2G demo app: forecast-aware hybrid agentic AI for a smart home in Surat.

    streamlit run app.py

Tabs: the problem, ask the house (request -> agents -> solver -> verifier), smart vs simple, results.
Pre-run examples (python -m b2g.demo.precompute) load instantly and offline; custom requests call the LLM.
"""

from __future__ import annotations

from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

from b2g import REPO_ROOT
from b2g.demo.core import EXAMPLES, load_examples, run_example, save_example, slug

st.set_page_config(page_title="Smart Home Energy Planner", page_icon="⚡", layout="wide")


def metric(col, label: str, value: str, note: str, good: bool | None = None) -> None:
    """A metric card whose note is green (good), red (bad) or grey (None), without the up/down arrow."""
    col.metric(label, value, note, delta_color="off" if good is None else "normal" if good else "inverse", delta_arrow="off")

# Fixed colours per entity (categorical slots of the reference palette, never re-assigned)
USE_COLORS = {"Base load": "#2a78d6", "AC": "#eb6834", "Car charging": "#1baf7a", "Battery charging": "#eda100"}
INK, MUTED, BAND = "#0b0b0b", "#8a8985", "#2a78d6"
FIELD_LABELS = {
    ("ev", "departure_time"): "🚗 Car leaves at", ("ev", "arrival_time"): "🚗 Car back at",
    ("ev", "target_soc"): "🚗 Car charge needed", ("ev", "max_power_kw"): "🚗 Max charging power",
    ("ev", "skip_charging"): "🚗 Skip car charging", ("battery", "reserve_soc"): "🔋 Battery backup reserve",
    ("battery", "allow_grid_charging"): "🔋 Battery may charge from grid",
    ("precool", "comfort_max_c"): "🌡️ Max room temperature", ("precool", "comfort_min_c"): "🌡️ Min room temperature",
    ("precool", "away_from"): "🏠 House empty from", ("precool", "away_until"): "🏠 Someone home again at",
    ("precool", "home_all_day"): "🏠 Someone home all day",
}
SYSTEM_NOTES = {
    "S1 simple rules": "charges the car as soon as it is home, AC on a thermostat, battery stores spare solar",
    "S4 our system": "LLM agents understand the request, the optimizer plans on forecasts, the verifier checks",
    "S5 perfect knowledge": "the optimizer with the real weather in advance (best possible, not achievable)",
    "S3 pure LLM": "the LLM writes the whole schedule itself (no optimizer, no verifier)",
}


# --- data -----------------------------------------------------------------------------------

@st.cache_data
def site_data() -> pd.DataFrame:
    from b2g.data.build import load_dataset
    return load_dataset()


@st.cache_data
def examples() -> list[dict]:
    return load_examples()


def hours(n: int = 96) -> list[float]:
    return [i * 0.25 for i in range(n)]


def hour_axis() -> alt.X:
    return alt.X("hour:Q", title="Hour of day", scale=alt.Scale(domain=[0, 24], nice=False),
                 axis=alt.Axis(values=list(range(0, 25, 3))))


def value_text(section: str, field: str, value) -> str:
    if field.endswith("_soc"):
        return f"{value:.0%}"
    if field.endswith("_c"):
        return f"{value:g} °C"
    if field.endswith("_kw"):
        return f"{value:g} kW"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


# --- charts ---------------------------------------------------------------------------------

def power_chart(s: dict) -> alt.Chart:
    """Stacked household uses vs the solar line, 15-min steps."""
    uses = pd.DataFrame({"hour": hours(), "Base load": s["base"], "AC": s["ac"], "Car charging": s["ev"],
                         "Battery charging": s["charge"]}).melt("hour", var_name="Use", value_name="kW")
    uses["order"] = uses["Use"].map({k: i for i, k in enumerate(USE_COLORS)})
    area = alt.Chart(uses).mark_area(interpolate="step-after", opacity=0.9).encode(
        x=hour_axis(), y=alt.Y("kW:Q", stack="zero", title="kW"),
        color=alt.Color("Use:N", scale=alt.Scale(domain=list(USE_COLORS), range=list(USE_COLORS.values())),
                        legend=alt.Legend(orient="top", title=None)),
        order="order:Q", tooltip=["hour", "Use", alt.Tooltip("kW:Q", format=".2f")])
    solar = alt.Chart(pd.DataFrame({"hour": hours(), "kW": s["pv"]})).mark_line(
        color=INK, strokeWidth=2.2, interpolate="step-after").encode(
        x="hour:Q", y="kW:Q", tooltip=[alt.Tooltip("hour"), alt.Tooltip("kW:Q", title="Solar kW", format=".2f")])
    return (area + solar).properties(height=300)


def temperature_chart(s: dict) -> alt.Chart:
    """Room vs outside temperature with the comfort band."""
    lo, hi = s["comfort"]
    room = pd.DataFrame({"hour": hours(97), "°C": s["temps"], "Series": "Room"})
    outside = pd.DataFrame({"hour": [h + 0.125 for h in hours()], "°C": s["t_out"], "Series": "Outside"})
    lines = alt.Chart(pd.concat([room, outside])).mark_line(strokeWidth=2).encode(
        x=hour_axis(), y=alt.Y("°C:Q", scale=alt.Scale(zero=False), title="°C"),
        color=alt.Color("Series:N", scale=alt.Scale(domain=["Room", "Outside"], range=["#eb6834", MUTED]),
                        legend=alt.Legend(orient="top", title=None)),
        strokeDash=alt.StrokeDash("Series:N", scale=alt.Scale(domain=["Room", "Outside"], range=[[1, 0], [5, 3]]), legend=None),
        tooltip=["hour", "Series", alt.Tooltip("°C:Q", format=".1f")])
    band = alt.Chart(pd.DataFrame({"lo": [lo], "hi": [hi]})).mark_rect(color=BAND, opacity=0.12).encode(y="lo:Q", y2="hi:Q")
    home = [{"start": i * 0.25, "end": (i + 1) * 0.25} for i, on in enumerate(s["occupied"]) if not on]
    away = alt.Chart(pd.DataFrame(home or [{"start": 0, "end": 0}])).mark_rect(color=MUTED, opacity=0.08).encode(
        x="start:Q", x2="end:Q")
    return (away + band + lines).properties(height=260)


def storage_chart(s: dict) -> alt.Chart:
    """Energy stored in the home battery and the car (kWh)."""
    levels = pd.concat([pd.DataFrame({"hour": hours(97), "kWh": s["e_bat"], "Store": "Home battery"}),
                        pd.DataFrame({"hour": hours(97), "kWh": s["e_ev"], "Store": "Car battery"})])
    return alt.Chart(levels).mark_line(strokeWidth=2).encode(
        x=hour_axis(), y=alt.Y("kWh:Q", title="kWh stored"),
        color=alt.Color("Store:N", scale=alt.Scale(domain=["Home battery", "Car battery"], range=["#eda100", "#1baf7a"]),
                        legend=alt.Legend(orient="top", title=None)),
        tooltip=["hour", "Store", alt.Tooltip("kWh:Q", format=".1f")]).properties(height=260)


# --- page sections --------------------------------------------------------------------------

def header() -> None:
    st.title("⚡ Smart Home Energy Planner — Surat")
    st.markdown("**Forecast-aware hybrid agentic AI for Building-to-Grid demand response.** "
                "LLM agents *understand* what you ask, an optimizer *plans* the day, a verifier *checks* it.")


def sidebar() -> None:
    with st.sidebar:
        st.header("How it works")
        st.markdown("1. **Forecast** tomorrow's solar and demand (LightGBM on weather forecasts)\n"
                    "2. **LLM agents** turn your request into precise rules\n"
                    "3. **Optimizer** (MILP) computes the cheapest schedule for car, battery and AC\n"
                    "4. **Verifier** checks physics, your wishes and the explanation; replans if needed\n"
                    "5. The plan is **replayed on the real weather** to score it")
        st.divider()
        st.caption("House in Surat: 5 kW rooftop solar, 10 kWh battery, 40 kWh electric car (7.4 kW charger), "
                   "1.5-ton AC, 8 kW grid limit. Weather data Feb 2024 – Sep 2026 (Open-Meteo). "
                   "Device sizes and tariff are placeholders.")
        st.caption("Base paper: El Makroum et al. (2025), *Agentic AI Home Energy Management System*, arXiv:2510.26603.")


def tab_problem() -> None:
    df = site_data()
    daily = df.drop(columns=["date", "slot"]).resample("D").sum() * 0.25
    irr_a, irr_f = daily["ghi_actual_wm2"] / 1000, daily["ghi_forecast_wm2"] / 1000
    c = st.columns(4)
    c[0].metric("Solar per day (5 kW panels)", f"{daily['pv_actual_kw'].mean():.1f} kWh")
    c[1].metric("House base demand per day", f"{daily['base_load_kw'].mean():.1f} kWh")
    c[2].metric("Day-ahead sunlight forecast error", f"{(irr_f - irr_a).abs().mean() / irr_a.mean() * 100:.1f} %")
    c[3].metric("Days of real Surat weather", f"{df['date'].nunique()}")

    left, right = st.columns(2)
    with left:
        st.subheader("Solar arrives at the wrong time")
        profile = df.groupby(df.index.hour + df.index.minute / 60)[["pv_actual_kw", "base_load_kw"]].mean().reset_index()
        profile.columns = ["hour", "Solar", "House demand"]
        long = profile.melt("hour", var_name="Series", value_name="kW")
        chart = alt.Chart(long).mark_area(opacity=0.35, interpolate="monotone", line=True).encode(
            x=hour_axis(), y=alt.Y("kW:Q", stack=None, title="Average kW"),
            color=alt.Color("Series:N", scale=alt.Scale(domain=["Solar", "House demand"], range=["#eda100", "#2a78d6"]),
                            legend=alt.Legend(orient="top", title=None)),
            tooltip=["Series", alt.Tooltip("hour:Q", format=".2f"), alt.Tooltip("kW:Q", format=".2f")]).properties(height=300)
        st.altair_chart(chart, width="stretch")
        st.caption("The sun peaks at noon, when nobody is home. People need power in the evening, when the sun is gone. "
                   "On top of this the car (7.4 kW) and the AC (1.6 kW) want power in the evening too.")
    with right:
        st.subheader("…and varies from day to day")
        solar = pd.DataFrame({"day": daily.index, "Actual": daily["pv_actual_kw"], "Forecast the day before": daily["pv_forecast_kw"]})
        long = solar.melt("day", var_name="Series", value_name="kWh")
        chart = alt.Chart(long).mark_line(strokeWidth=1.2).encode(
            x=alt.X("day:T", title=None), y=alt.Y("kWh:Q", title="Solar kWh per day"),
            color=alt.Color("Series:N", scale=alt.Scale(domain=["Actual", "Forecast the day before"], range=["#2a78d6", "#eb6834"]),
                            legend=alt.Legend(orient="top", title=None)),
            tooltip=[alt.Tooltip("day:T"), "Series", alt.Tooltip("kWh:Q", format=".1f")]).properties(height=300)
        st.altair_chart(chart, width="stretch")
        st.caption("Monsoon clouds (June–September) make solar drop suddenly, and forecasts miss some of it.")
    st.info("**The idea:** shift flexible loads to good hours — charge the car and the battery from solar, "
            "**pre-cool** the house in the afternoon while nobody is home — and let AI plan it from a plain request.")


def show_plan(data: dict) -> None:
    """One request: what was understood, the answer, the day's charts and the agents' steps."""
    st.markdown(f"> 💬 *{data['request']}*  \n📅 **{data['weekday']} {data['date']}**")
    if not data.get("ok"):
        st.error(f"The agents did not finish: {data.get('error')}")
        return
    summary, series, verification = data["plan_summary"], data["series"], data["verification"] or {}
    outcome = data["comparison"]["S4 our system"]
    ev = summary["ev"]
    c = st.columns(4)
    if ev["departure"] != "no trip":
        metric(c[0], "🚗 Car at departure", f"{ev['kwh_at_departure']} / {ev['target_kwh']} kWh",
               "ready ✓" if ev["target_met"] else "short", ev["target_met"])
    else:
        metric(c[0], "🚗 Car", "no trip", f"charging {ev['charging']}")
    band = summary["room"]["comfort_band_c"]
    warm = summary["room"]["max_temp_when_home_c"]
    metric(c[1], "🌡️ Warmest while home", f"{warm} °C" if warm is not None else "nobody home", f"wish ≤ {band[1]:g} °C",
           None if warm is None or warm <= band[1] + 0.05 else False)
    metric(c[2], "💰 Electricity (real day)", f"₹{outcome['electricity_cost']:.0f}", f"peak {outcome['peak_import_kw']:.1f} kW")
    metric(c[3], "🛡️ Verifier", "passed ✓" if verification.get("passed") else "problems",
           f"{len(verification.get('warnings_to_tell_the_person', []))} warning(s) disclosed")

    left, right = st.columns([2, 3])
    with left:
        st.subheader("What the AI understood")
        rows = [{"Rule": FIELD_LABELS.get((sec, f), f"{sec}.{f}"), "Value": value_text(sec, f, v)}
                for sec, fields in data["constraints"].items() for f, v in fields.items()]
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        else:
            st.write("No changes — the usual routine applies.")
        st.subheader("Answer to you")
        st.success(data["answer"])
        if data.get("replans") or data.get("explanation_fixed"):
            st.caption(f"Verifier sent the plan back {data['replans']} time(s)"
                       + ("; the explanation was corrected." if data.get("explanation_fixed") else "."))
    with right:
        st.subheader("Where the power goes (black line = solar)")
        st.altair_chart(power_chart(series), width="stretch")
        a, b = st.columns(2)
        with a:
            st.markdown("**Room temperature** (blue band = comfort, grey = nobody home)")
            st.altair_chart(temperature_chart(series), width="stretch")
        with b:
            st.markdown("**Energy stored**")
            st.altair_chart(storage_chart(series), width="stretch")

    with st.expander("🔍 See the agents think — step by step"):
        for step in data["trace"]:
            st.markdown(f"**Step {step['step']} · {step['action']}**"
                        + (f" → *{step['agent']}*" if step.get("agent") else ""))
            if step["thought"]:
                st.caption(step["thought"])
            if step.get("agent_answer") is not None:
                st.json(step["agent_answer"])
            elif step["action"] not in ("FINISH",):
                st.code(step["observation"][:1500], language="json")


def tab_ask() -> None:
    saved = examples()
    mode = st.radio("Choose", ["Pre-run example (instant, works offline)", "Type my own request (live AI, ~30 s)"],
                    horizontal=True, label_visibility="collapsed")
    if mode.startswith("Pre-run"):
        if not saved:
            st.warning("No pre-run examples yet. Run `python -m b2g.demo.precompute` once.")
            return
        titles = [d["title"] for d in saved]
        choice = st.selectbox("Example", titles)
        show_plan(saved[titles.index(choice)])
        return

    c1, c2 = st.columns([1, 3])
    day = c1.date_input("Day to plan", value=date(2026, 5, 6), min_value=date(2026, 1, 2), max_value=date(2026, 9, 30))
    request = c2.text_area("Your request", value="I'm leaving at 6:30 tomorrow and need the car at 100%. Keep the room under 26 °C.",
                           height=80)
    if st.button("⚡ Plan my day", type="primary"):
        with st.status("Agents at work: reading the forecast, asking the specialists, optimizing, verifying…", expanded=False) as status:
            try:
                data = run_example(day.isoformat(), request, title=f"Custom: {request[:40]}")
                save_example(data, name=f"custom_{slug(request[:40])}_{day:%Y%m%d}")
                st.session_state["custom"] = data
                status.update(label="Done", state="complete")
            except Exception as e:  # network / provider problems during a live demo
                status.update(label="Could not reach the AI service", state="error")
                st.error(f"{type(e).__name__}: {e}. Use a pre-run example instead (it works offline).")
    if "custom" in st.session_state:
        show_plan(st.session_state["custom"])


def tab_compare() -> None:
    saved = [d for d in examples() if d.get("comparison")]
    if not saved:
        st.warning("No pre-run examples yet.")
        return
    titles = [d["title"] for d in saved]
    data = saved[titles.index(st.selectbox("Example day", titles, key="compare"))]
    st.markdown(f"> 💬 *{data['request']}*  \n📅 {data['weekday']} {data['date']} — every system gets the same "
                "wishes and is scored on the **real** weather of that day.")
    rows = []
    for name, m in data["comparison"].items():
        rows.append({"System": name, "Electricity ₹": round(m["electricity_cost"]), "Total ₹ (incl. comfort & car penalties)": round(m["total_cost"]),
                     "Discomfort °C·h": round(m["comfort_dh"], 2), "Car short kWh": round(m["ev_unmet_kwh"], 1),
                     "Peak grid kW": round(m["peak_import_kw"], 1), "Problems": "; ".join(m["violations"][:2]) or "none"})
    table = pd.DataFrame(rows)
    st.dataframe(table, hide_index=True, width="stretch")
    order = list(table["System"])
    colors = ["#8a8985" if "S1" in s else "#2a78d6" if "S4" in s else "#1baf7a" if "S5" in s else "#e34948" for s in order]
    a, b = st.columns(2)
    for col, metric, title in ((a, "Electricity ₹", "Electricity bill for the day (₹)"),
                               (b, "Discomfort °C·h", "Discomfort while home (°C·h, lower is better)")):
        chart = alt.Chart(table).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
            x=alt.X("System:N", sort=order, title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y(f"{metric}:Q", title=None), color=alt.Color("System:N", scale=alt.Scale(domain=order, range=colors), legend=None),
            tooltip=["System", metric]).properties(height=260, title=title)
        col.altair_chart(chart, width="stretch")
    for name in order:
        st.caption(f"**{name}** — {SYSTEM_NOTES.get(name, '')}")
    if data.get("s3"):
        s3 = data["s3"]
        st.subheader("⚠️ Why not let the LLM do the maths itself? (S3)")
        st.error(f"The pure-LLM schedule broke **{s3['errors']} physical rules** — for example: "
                 + "; ".join(s3["error_examples"][:3]) + ".")
        if s3["warnings"]:
            st.markdown("Wishes it missed: " + "; ".join(s3["warnings"]).replace("degC", "°C"))
        st.caption("Its electricity bill looks low only because it did not do the job: the car left short and the house got hot.")
        if s3["reasoning"]:
            st.caption(f"Its own reasoning said: “{s3['reasoning'][:400]}…” — but the schedule it returned did something else.")


def tab_results() -> None:
    left, right = st.columns(2)
    with left:
        st.subheader("Forecast accuracy (test: Jan–Sep 2026)")
        m3 = pd.read_csv(REPO_ROOT / "results" / "m3_forecast_metrics.csv")
        m3 = m3[(m3["split"] == "test") & (m3["season"] == "all")]
        names = {"persistence": "Same as yesterday", "physics": "Weather-forecast physics", "weekly": "Same day last week", "lgbm": "LightGBM (ML)"}
        m3 = m3.assign(Target=m3["target"].map({"pv": "Solar", "load": "House demand"}), Model=m3["model"].map(names),
                       **{"Error %": m3["nmae_pct"].map("{:.1f}".format)})[["Target", "Model", "Error %"]]
        st.dataframe(m3, hide_index=True, width="stretch")
        st.caption("Error = average absolute error as % of the average value (nMAE). Lower is better.")
    with right:
        st.subheader("One hot week (4–10 May 2026), daily averages")
        m5 = pd.read_csv(REPO_ROOT / "results" / "m5_baselines.csv")
        week = m5.groupby("system", sort=False).agg(**{"Total ₹": ("total_cost", "mean"), "Electricity ₹": ("electricity_cost", "mean"),
                                                       "Discomfort °C·h": ("comfort_dh", "mean"), "Peak kW": ("peak_import_kw", "mean"),
                                                       "Solar used %": ("self_consumption_pct", "mean")}).round(1).reset_index()
        st.dataframe(week.rename(columns={"system": "System"}), hide_index=True, width="stretch")
        st.caption("S1 rules · S2 forecast + optimizer (two forecasters) · S5 perfect knowledge. No LLM involved here.")
    figure = REPO_ROOT / "results" / "figures" / "m3_error_by_month.png"
    if figure.exists():
        st.image(str(figure), caption="Forecast error by month: the monsoon is hard, and the weather forecast's own error changed in 2026.")
    st.subheader("Honest limitations")
    st.markdown("- Device sizes, tariff and house heat model are **placeholders** (in `b2g/config/default.yaml`).\n"
                "- House base demand is **synthetic**; 'actual' weather is ERA5 reanalysis, not a rooftop measurement.\n"
                "- Results are from a few example days and one LLM (Qwen 3.8 27B on Groq's free tier), not a large study.")


def main() -> None:
    header()
    sidebar()
    tabs = st.tabs(["☀️ The problem", "🏠 Ask the house", "⚖️ Smart vs simple", "📊 Results"])
    with tabs[0]:
        tab_problem()
    with tabs[1]:
        tab_ask()
    with tabs[2]:
        tab_compare()
    with tabs[3]:
        tab_results()


main()
