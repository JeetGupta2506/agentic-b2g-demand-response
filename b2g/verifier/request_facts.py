"""Rule-based reading of explicit facts in a request: times, relative shifts, percentages, temperatures,
powers and a few phrases. Used to check that the agents neither ignored nor invented values.

Deliberately simple and explainable: it understands numbers ("7", "2 pm", "19:30", "90%", "26 °C",
"an hour earlier"), not vague wishes ("a bit cooler"). A bare hour like "7" is ambiguous, so it
yields both 07:00 and 19:00 as candidates.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_NOT_TIME = r"(?!\s*(?:%|percent|per cent|°|degrees?|deg\b|celsius|kwh|kw\b|hours?|hrs?|minutes?|mins?|c\b|:\d))"
_TIME_PATTERNS = [
    re.compile(r"\b(\d{1,2}):(\d{2})\s*(am|pm|a\.m\.|p\.m\.)?", re.I),
    re.compile(r"\b(\d{1,2})()\s*(am|pm|a\.m\.|p\.m\.|o'?clock)", re.I),
    re.compile(r"\b(?:at|by|from|until|till|til|before|after|around|instead of|leave|leaving|back|return)\s+(\d{1,2})(?![\d.])()()" + _NOT_TIME, re.I),
]
_SHIFT = re.compile(r"\b(half an|an|a|one|two|three|\d+(?:\.\d+)?)\s*(hours?|hrs?|minutes?|mins?)\s*(earlier|sooner|later)\b", re.I)
_HALF_HOUR = re.compile(r"\bhalf an hour\s*(earlier|sooner|later)\b", re.I)
_PERCENT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*(?:%|percent|per cent)", re.I)
_TEMP_UNIT = re.compile(r"(\d{1,2}(?:\.\d)?)\s*(?:°\s*c?|degrees?(?:\s*c(?:elsius)?)?|deg\b|celsius)", re.I)
_TEMP_WORD = re.compile(r"\b(?:under|below|above|over|max(?:imum)?|at most|at least|no more than|not more than|"
                        r"cooler than|warmer than|between)\s+(\d{1,2}(?:\.\d)?)\b(?!\s*(?:%|percent|am|pm|kw|:))", re.I)
_KW = re.compile(r"(\d+(?:\.\d+)?)\s*kw\b(?!h)", re.I)
_WORDS = {"half an": 0.5, "an": 1, "a": 1, "one": 1, "two": 2, "three": 3}

PHRASES = {
    "full": re.compile(r"\bfull(?:y)?\b|\b100\s*%", re.I),
    "home_all_day": re.compile(r"home all day|all day at home|whole day at home|working from home all day|stay(?:ing)? (?:at )?home|"
                               r"not going (?:out|anywhere|to work|to the office)|day off|won'?t (?:go|leave)", re.I),
    "solar_only": re.compile(r"(?:only|just) (?:from|with|on|by) (?:the )?(?:sun|solar)|solar only|not from the grid|no grid charging|"
                             r"don'?t charge (?:it|the battery) from the grid", re.I),
    "grid_charging_ok": re.compile(r"(?<!not )(?<!don't )charge (?:the battery |it )?from the grid", re.I),
    "skip_charging": re.compile(r"(?:don'?t|do not|no need to|not) charge (?:the )?(?:car|ev)|skip (?:the )?(?:car|ev)? ?charging", re.I),
}


def hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


@dataclass
class RequestFacts:
    times: list[set[str]] = field(default_factory=list)     # one candidate set per mention
    time_texts: list[str] = field(default_factory=list)     # the words each mention came from
    shifts_min: list[int] = field(default_factory=list)     # relative shifts, e.g. -60 for "an hour earlier"
    fractions: list[float] = field(default_factory=list)    # 90 % -> 0.9
    temperatures: list[float] = field(default_factory=list)
    powers_kw: list[float] = field(default_factory=list)
    phrases: set[str] = field(default_factory=set)

    def all_times(self) -> set[str]:
        return set().union(*self.times) if self.times else set()


def _time_candidates(hour: int, minute: int, suffix: str) -> set[str]:
    suffix = suffix.lower().replace(".", "")
    if suffix in ("am", "pm"):
        hour = hour % 12 + (12 if suffix == "pm" else 0)
        return {hhmm(hour * 60 + minute)}
    if hour > 12 or hour == 0:
        return {hhmm(hour * 60 + minute)} if hour <= 24 else set()
    return {hhmm(hour * 60 + minute), hhmm((hour % 12 + 12) * 60 + minute)}


def extract_facts(request: str) -> RequestFacts:
    """All explicit facts in the request text."""
    facts = RequestFacts()
    taken: list[tuple[int, int]] = []
    for pattern in _TIME_PATTERNS:
        for m in pattern.finditer(request):
            span = (m.start(1), m.end(1))
            if any(a < span[1] and span[0] < b for a, b in taken):
                continue
            hour, minute = int(m.group(1)), int(m.group(2) or 0)
            candidates = _time_candidates(hour, minute, m.group(3) or "")
            if candidates and minute < 60:
                taken.append(span)
                facts.times.append(candidates)
                facts.time_texts.append(m.group(0).strip())
    for m in _HALF_HOUR.finditer(request):
        facts.shifts_min.append(-30 if m.group(1).lower() in ("earlier", "sooner") else 30)
    for m in _SHIFT.finditer(request):
        amount, unit, direction = m.group(1).lower(), m.group(2).lower(), m.group(3).lower()
        if amount == "half an":
            continue                                         # handled above
        value = _WORDS.get(amount) or float(amount)
        minutes = round(value * (60 if unit.startswith(("hour", "hr")) else 1))
        facts.shifts_min.append(-minutes if direction in ("earlier", "sooner") else minutes)
    facts.fractions = [float(m.group(1)) / 100 for m in _PERCENT.finditer(request)]
    temps = {float(m.group(1)) for m in _TEMP_UNIT.finditer(request)}
    temps |= {float(m.group(1)) for m in _TEMP_WORD.finditer(request) if 15 <= float(m.group(1)) <= 35}
    facts.temperatures = sorted(temps)
    facts.powers_kw = [float(m.group(1)) for m in _KW.finditer(request)]
    facts.phrases = {name for name, pattern in PHRASES.items() if pattern.search(request)}
    return facts
