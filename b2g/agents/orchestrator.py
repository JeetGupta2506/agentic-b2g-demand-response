"""S4 orchestrator: a ReAct loop in the original's "ACTION: NAME | key=value" format.

The LLM understands the request and delegates to specialist agents, which return constraint JSON
(validated with pydantic, one repair attempt, else defaults). RUN_SOLVER applies the merged
constraints and lets the MILP compute the schedule; the LLM never computes schedules itself.
With verification on (M7), VERIFY checks the latest plan; FINISH is accepted only after VERIFY on the
latest plan and, while errors remain, only once the replans (max 3) are used up. The final explanation
is checked against what was observed: one rewrite, then a generated explanation; remaining problems
are always appended. Every step is recorded (`save_trace` writes trace.json and a readable trace.md).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from b2g.agents import tools
from b2g.agents.llm_client import LLMClient, get_client
from b2g.agents.schemas import AGENT_SCHEMAS, DayConstraints
from b2g.sim.day import Assets, DayData, State
from b2g.solver.milp import Plan
from b2g.verifier.checks import Report, check_explanation, fallback_explanation, observed_values, verify

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
AGENT_FIELDS = {"ev_agent": "ev", "battery_agent": "battery", "precool_agent": "precool"}
ACTIONS = ("GET_FORECAST", "GET_CALENDAR", "CALL_AGENT", "RUN_SOLVER", "VERIFY", "FINISH")
_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)
_ACTION_LINE = re.compile(r"^[ \t*_`]*ACTION[*_`]*\s*:\s*(.+)$", re.I | re.M)


def strip_think(text: str | None) -> str:
    """Remove <think>...</think> blocks some reasoning models put in their answer."""
    return _THINK.sub("", text or "").strip()


def parse_action(text: str) -> tuple[str, dict[str, str]] | None:
    """First 'ACTION: NAME | key=value | ...' line -> (NAME, params); FINISH's summary runs to the end."""
    clean = strip_think(text)
    match = _ACTION_LINE.search(clean)
    if not match:
        return None
    name, _, tail = match.group(1).strip().strip("`*").partition("|")
    name = name.strip().upper()
    if name == "FINISH":
        at = clean.find("summary=", match.start())
        return name, ({"summary": clean[at + len("summary="):].strip()} if at >= 0 else {})
    params: dict[str, str] = {}
    key = None
    for part in tail.split("|"):
        if "=" in part:
            key, _, value = part.partition("=")
            key = key.strip()
            params[key] = value
        elif key:                                   # a '|' inside a value
            params[key] += "|" + part
    return name, {k: v.strip() for k, v in params.items()}


def until_action(text: str) -> str:
    """The reply up to the end of its first ACTION line (drops anything a model writes after it)."""
    clean = strip_think(text)
    match = _ACTION_LINE.search(clean)
    if not match or match.group(1).strip().upper().startswith("FINISH"):
        return clean
    return clean[:match.end()]


def extract_json(text: str) -> dict[str, Any]:
    """The JSON object in an agent's answer (plain, or inside a ``` block)."""
    clean = strip_think(text)
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", clean, re.S)
    candidate = fenced.group(1) if fenced else clean[clean.find("{"):clean.rfind("}") + 1]
    if not candidate:
        raise ValueError("no JSON object found")
    value = json.loads(candidate)
    if not isinstance(value, dict):
        raise ValueError("the answer must be a JSON object")
    return value


def describe_error(error: Exception) -> str:
    """Short, model-readable reason an agent answer was rejected."""
    if isinstance(error, ValidationError):
        return "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'answer'}: {e['msg']}" for e in error.errors())
    return str(error).splitlines()[0]


@dataclass
class OrchestratorResult:
    request: str
    success: bool
    constraints: DayConstraints
    plan: Plan | None
    day_assets: Assets | None
    plan_summary: dict[str, Any] | None
    final_summary: str
    steps: int
    trace: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    report: Report | None = None            # last verification of the final plan (None without verifier)
    replans: int = 0
    explanation_issues: list[str] = field(default_factory=list)
    explanation_fallback: bool = False


class Orchestrator:
    """Plans one day for one request, using the day-ahead `forecast` and the start `state`."""

    def __init__(self, assets: Assets, forecast: DayData, state: State, client: LLMClient | None = None,
                 max_steps: int = 12, verify: bool = True, max_replans: int = 3):
        self.assets, self.forecast, self.state = assets, forecast, state
        self.client = client or get_client()
        self.max_steps = max_steps
        self.use_verifier, self.max_replans = verify, max_replans
        self.constraints = DayConstraints()
        self.plan: Plan | None = None
        self.day_assets: Assets | None = None
        self.plan_summary: dict[str, Any] | None = None
        self.trace: list[dict[str, Any]] = []
        self.report: Report | None = None        # verification of the latest plan (None = not verified yet)
        self.replans = 0                         # RUN_SOLVER calls after a failed verification
        self.rewrites = 0
        self.observations: list[str] = []
        self.request = ""
        self.explanation_issues: list[str] = []
        self.explanation_fallback = False

    @property
    def replans_left(self) -> int:
        return self.max_replans - self.replans

    def _llm(self, messages: list[dict[str, str]], tag: str, max_tokens: int) -> str:
        result = self.client.complete({"messages": messages, "max_tokens": max_tokens}, timeout=120, tag=tag)
        return result["choices"][0]["message"].get("content") or ""

    def _agent_context(self, agent: str) -> dict[str, Any]:
        """The defaults (and the forecast details) relevant to one agent."""
        cal, fc = tools.calendar_info(self.assets, self.forecast.day), tools.forecast_summary(self.forecast)
        base = {"date": cal["date"], "weekday": cal["weekday"]}
        if agent == "ev_agent":
            return {**base, "defaults": cal["ev"]}
        if agent == "battery_agent":
            return {**base, "defaults": cal["home_battery"], "pv_forecast_kwh": fc["pv_forecast_kwh"]}
        return {**base, "defaults": cal["comfort"], "outdoor_temp_forecast_c": fc["outdoor_temp_c"]}

    def call_agent(self, agent: str, user_request: str) -> tuple[str, dict[str, Any]]:
        """Ask one specialist; validate; one repair attempt; defaults if it still fails."""
        schema = AGENT_SCHEMAS[agent]
        messages = [{"role": "system", "content": (PROMPTS_DIR / f"{agent}.md").read_text(encoding="utf-8")},
                    {"role": "user", "content": f"Context:\n{json.dumps(self._agent_context(agent), indent=1)}\n\n"
                                                f"Request: {user_request}"}]
        record: dict[str, Any] = {"agent": agent, "request": user_request, "attempts": []}
        for attempt in range(2):
            answer = self._llm(messages, f"s4:{agent}", 2000)
            try:
                parsed = schema.model_validate(extract_json(answer))
                record["attempts"].append({"answer": strip_think(answer), "valid": True})
                break
            except (ValueError, ValidationError) as e:
                error = describe_error(e)
                record["attempts"].append({"answer": strip_think(answer), "valid": False, "error": error})
                messages += [{"role": "assistant", "content": strip_think(answer)},
                             {"role": "user", "content": f"Your answer was not valid: {error}\n"
                                                         "Answer again with a single corrected JSON object."}]
        else:
            parsed = schema(reasoning=f"{agent} gave no valid answer twice; defaults used")
            record["fallback_to_defaults"] = True
        setattr(self.constraints, AGENT_FIELDS[agent], parsed)
        record["constraints"] = parsed.model_dump(exclude_defaults=True)
        observation = {"agent": agent, "constraints": record["constraints"]}
        if record.get("fallback_to_defaults"):
            observation["warning"] = "agent failed twice; defaults kept"
        return json.dumps(observation), record

    def execute(self, name: str, params: dict[str, str], request: str) -> tuple[str, dict[str, Any] | None]:
        """Run one action; returns the observation text and an optional sub-record for the trace."""
        if name == "GET_FORECAST":
            return json.dumps(tools.forecast_summary(self.forecast)), None
        if name == "GET_CALENDAR":
            return json.dumps(tools.calendar_info(self.assets, self.forecast.day)), None
        if name == "CALL_AGENT":
            agent = params.get("agent_name", "").strip()
            if agent not in AGENT_SCHEMAS:
                return f"Unknown agent '{agent}'. Use one of: {', '.join(AGENT_SCHEMAS)}.", None
            return self.call_agent(agent, params.get("user_request") or request)
        if name == "RUN_SOLVER":
            if self.use_verifier and self.report is not None and not self.report.passed:
                if self.replans_left <= 0:
                    return "No replans left. FINISH now and tell the person about every remaining problem.", None
                self.replans += 1
            try:
                self.plan, self.day_assets, self.plan_summary = tools.run_solver(self.assets, self.forecast, self.state, self.constraints)
            except Exception as e:  # report to the LLM instead of crashing the run
                return f"Solver error: {e}", None
            self.report = None                   # the new plan is not verified yet
            return json.dumps(self.plan_summary), None
        if name == "VERIFY":
            if self.plan is None:
                return "Nothing to verify yet: RUN_SOLVER first.", None
            self.report = verify(self.assets, self.day_assets, self.forecast, self.plan.actions, self.state,
                                 request, self.constraints)
            result = {**self.report.as_dict(), "replans_left": self.replans_left}
            if not self.report.passed:
                result["instruction"] = ("Ask the named agent again with the original request and the problem, then RUN_SOLVER and VERIFY."
                                         if self.replans_left > 0 else "No replans left: FINISH and tell the person about every problem.")
            elif self.report.warnings:
                result["instruction"] = "Passed. FINISH, and tell the person about every warning honestly."
            return json.dumps(result), None
        return f"Unknown action '{name}'. Use one of: {', '.join(ACTIONS)}.", None

    def finish(self, summary: str) -> tuple[bool, str]:
        """Gate FINISH. Returns (accepted, final text or the observation explaining why not)."""
        if self.plan is None:
            return False, "You must RUN_SOLVER before FINISH."
        if not self.use_verifier:
            return True, summary
        if self.report is None:
            return False, "VERIFY the latest plan before FINISH."
        if not self.report.passed and self.replans_left > 0:
            return False, (f"Verification failed and you have {self.replans_left} replans left: ask the named agent again, "
                           "then RUN_SOLVER and VERIFY.")
        times, numbers = observed_values(self.observations + [self.request])
        issues = check_explanation(summary, self.report, self.plan_summary, times, numbers)
        if issues and self.rewrites < 1:
            self.rewrites += 1
            self.explanation_issues += [i.message for i in issues]
            problems = "; ".join(i.message for i in issues)
            return False, (f"Your explanation has problems: {problems}. Rewrite it using only numbers from the observations "
                           "and mention every warning: ACTION: FINISH | summary=<corrected explanation>")
        if issues:
            self.explanation_issues += [i.message for i in issues]
            self.explanation_fallback = True
            return True, fallback_explanation(self.plan_summary, self.report)
        if self.report.errors:  # out of replans: the person must still hear about every problem
            summary += "\n\nProblems the system could not fix:\n" + "\n".join(f"- {i.message}" for i in self.report.errors)
        return True, summary

    def run(self, request: str) -> OrchestratorResult:
        """The ReAct loop; stops at an accepted FINISH or after max_steps."""
        self.request = request
        prompt = "orchestrator.md" if self.use_verifier else "orchestrator_no_verify.md"
        system = (PROMPTS_DIR / prompt).read_text(encoding="utf-8")
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": f"Plan for {self.forecast.day:%A %d %B %Y}. Request: {request}"}]
        for step in range(1, self.max_steps + 1):
            text = self._llm(messages, "s4:orchestrator", 1500)
            action = parse_action(text)
            entry: dict[str, Any] = {"step": step, "llm": strip_think(text)}
            if action is None:
                observation = "No ACTION found. Reply with 'Thought: ...' and exactly one 'ACTION: ...' line."
            else:
                name, params = action
                entry.update(action=name, params=params)
                if name == "FINISH":
                    accepted, observation = self.finish(params.get("summary", ""))
                    if accepted:
                        entry["observation"] = "done"
                        self.trace.append(entry)
                        return self._result(request, True, observation, step)
                else:
                    observation, record = self.execute(name, params, request)
                    self.observations.append(observation)   # only tool results ground the explanation
                    if record:
                        entry["agent_call"] = record
            entry["observation"] = observation
            self.trace.append(entry)
            messages += [{"role": "assistant", "content": until_action(text)},
                         {"role": "user", "content": f"Observation: {observation}"}]
        return self._result(request, False, "", self.max_steps, error=f"no FINISH within {self.max_steps} steps")

    def _result(self, request: str, success: bool, summary: str, steps: int, error: str | None = None) -> OrchestratorResult:
        return OrchestratorResult(request, success, self.constraints, self.plan, self.day_assets, self.plan_summary,
                                  summary, steps, self.trace, error, self.report, self.replans,
                                  self.explanation_issues, self.explanation_fallback)


def save_trace(result: OrchestratorResult, out_dir: Path) -> tuple[Path, Path]:
    """Write trace.json (everything) and trace.md (readable) to out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    data = {"request": result.request, "success": result.success, "error": result.error, "steps": result.steps,
            "constraints_changed": result.constraints.changes(),
            "agent_reasoning": {k: getattr(result.constraints, k).reasoning for k in ("ev", "battery", "precool")},
            "plan_summary": result.plan_summary, "final_summary": result.final_summary,
            "verification": result.report.as_dict() if result.report else None, "replans": result.replans,
            "explanation_issues": result.explanation_issues, "explanation_fallback": result.explanation_fallback,
            "trace": result.trace}
    json_path = out_dir / "trace.json"
    json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = ["# S4 reasoning trace", "", f"**Request:** {result.request}", "",
             f"**Outcome:** {'finished' if result.success else 'did not finish: ' + str(result.error)} in {result.steps} steps", ""]
    for entry in result.trace:
        lines += [f"## Step {entry['step']}: {entry.get('action', 'no action')}", "", entry["llm"].strip(), ""]
        if "agent_call" in entry:
            call = entry["agent_call"]
            for i, attempt in enumerate(call["attempts"], 1):
                status = "valid" if attempt["valid"] else f"invalid ({attempt.get('error', '')[:200]})"
                lines += [f"> **{call['agent']}**, attempt {i}: {status}", ">", "> ```", *[f"> {l}" for l in attempt["answer"].splitlines()], "> ```", ""]
        if entry.get("action") != "FINISH":
            obs = entry["observation"]
            try:
                obs = json.dumps(json.loads(obs), indent=1, ensure_ascii=False)
            except (ValueError, TypeError):
                pass
            lines += ["**Observation:**", "", "```", obs, "```", ""]
    lines += ["## Constraints that differ from the defaults", "", "```json",
              json.dumps(result.constraints.changes(), indent=1), "```", ""]
    if result.report is not None:
        lines += ["## Final verification", "", f"Replans used: {result.replans}", "", "```json",
                  json.dumps(result.report.as_dict(), indent=1, ensure_ascii=False), "```", ""]
    if result.explanation_issues:
        lines += ["## Explanation problems caught", "", *[f"- {m}" for m in result.explanation_issues],
                  "", f"Generated fallback explanation used: {result.explanation_fallback}", ""]
    lines += ["## Answer to the person", "", result.final_summary or "(none)", ""]
    md_path = out_dir / "trace.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path
