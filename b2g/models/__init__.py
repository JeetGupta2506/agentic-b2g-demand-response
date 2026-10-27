"""M4 physical models on the 96 x 15-min day grid (kW, kWh, degC). Shared by solver, simulator, verifier."""

from __future__ import annotations

import numpy as np

SLOTS = 96
DT_H = 0.25  # hours per slot
TOL = 1e-6   # numerical tolerance for checks (kW / kWh / degC)


def as_profile(values, name: str = "profile") -> np.ndarray:
    """A 96-slot float array, or ValueError."""
    array = np.asarray(values, dtype=float)
    if array.shape != (SLOTS,):
        raise ValueError(f"{name} must have {SLOTS} values, got shape {array.shape}")
    return array


def hhmm_to_slot(text: str) -> int:
    """'08:00' -> 32 (slot starting at that time); must be on a 15-min boundary."""
    hours, minutes = (int(x) for x in text.split(":"))
    if minutes % 15:
        raise ValueError(f"{text} is not on a 15-min boundary")
    return hours * 4 + minutes // 15
