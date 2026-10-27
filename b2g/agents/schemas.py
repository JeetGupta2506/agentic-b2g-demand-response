"""Constraint JSON the specialist agents may return (validated with pydantic).

Every field is optional: an omitted field keeps the configured default, so an agent only states
what the person's request changes. Times are "HH:MM" on 15-min boundaries ("24:00" = end of day),
fractions are 0..1, temperatures degC, powers kW.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def check_hhmm(value: str | None) -> str | None:
    """'07:00' ok; '7:00' normalised to '07:00'; '07:10' or '25:00' rejected."""
    if value is None:
        return None
    try:
        hours, minutes = (int(x) for x in value.strip().split(":"))
    except ValueError:
        raise ValueError(f"'{value}' is not a time like 07:00") from None
    if not (0 <= hours <= 24 and 0 <= minutes < 60) or (hours == 24 and minutes):
        raise ValueError(f"'{value}' is not a valid time of day")
    if minutes % 15:
        raise ValueError(f"'{value}' is not on a 15-minute step; use e.g. 07:00 or 07:15")
    return f"{hours:02d}:{minutes:02d}"


def minutes(value: str) -> int:
    hours, mins = (int(x) for x in value.split(":"))
    return hours * 60 + mins


class _Constraints(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reasoning: str = ""


class EVConstraints(_Constraints):
    departure_time: str | None = None
    arrival_time: str | None = None
    target_soc: float | None = Field(None, ge=0.1, le=1.0)
    max_power_kw: float | None = Field(None, gt=0, le=22)
    skip_charging: bool | None = None

    @field_validator("departure_time", "arrival_time")
    @classmethod
    def valid_times(cls, value: str | None) -> str | None:
        return check_hhmm(value)

    @model_validator(mode="after")
    def valid_order(self) -> "EVConstraints":
        if self.departure_time and self.arrival_time and minutes(self.departure_time) >= minutes(self.arrival_time):
            raise ValueError("departure_time must be before arrival_time")
        return self


class BatteryConstraints(_Constraints):
    reserve_soc: float | None = Field(None, ge=0.0, le=0.9)
    allow_grid_charging: bool | None = None


class PrecoolConstraints(_Constraints):
    comfort_min_c: float | None = Field(None, ge=16, le=30)
    comfort_max_c: float | None = Field(None, ge=18, le=32)
    away_from: str | None = None
    away_until: str | None = None
    home_all_day: bool | None = None

    @field_validator("away_from", "away_until")
    @classmethod
    def valid_times(cls, value: str | None) -> str | None:
        return check_hhmm(value)

    @model_validator(mode="after")
    def valid_combination(self) -> "PrecoolConstraints":
        if self.comfort_min_c is not None and self.comfort_max_c is not None and self.comfort_min_c >= self.comfort_max_c:
            raise ValueError("comfort_min_c must be below comfort_max_c")
        if self.away_from and self.away_until and minutes(self.away_from) >= minutes(self.away_until):
            raise ValueError("away_from must be before away_until")
        if self.home_all_day and (self.away_from or self.away_until):
            raise ValueError("home_all_day cannot be combined with away_from/away_until")
        return self


AGENT_SCHEMAS = {"ev_agent": EVConstraints, "battery_agent": BatteryConstraints, "precool_agent": PrecoolConstraints}


class DayConstraints(BaseModel):
    """Everything the agents decided for one day (defaults where an agent was not called)."""

    ev: EVConstraints = EVConstraints()
    battery: BatteryConstraints = BatteryConstraints()
    precool: PrecoolConstraints = PrecoolConstraints()

    def changes(self) -> dict[str, dict]:
        """Only the fields that differ from the defaults (for traces and RQ3 scoring)."""
        return {name: getattr(self, name).model_dump(exclude_defaults=True, exclude={"reasoning"})
                for name in ("ev", "battery", "precool")}
