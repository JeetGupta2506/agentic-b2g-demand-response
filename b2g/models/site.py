"""Site power balance and grid exchange (plan section 4):

    G_imp - G_exp = Base + P_ev + P_cool + Pc - Pd - P_pv,   0 <= G_imp <= G_imp_max,   G_exp >= 0

All profiles are 96-slot kW arrays; energies are kW x 0.25 h; money in the tariff's currency.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from b2g.models import DT_H, SLOTS, TOL, as_profile


@dataclass(frozen=True)
class GridParams:
    import_limit_kw: float
    export_price: float  # per kWh, same currency as the buy price

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "GridParams":
        return cls(**cfg["grid"])


def net_load_kw(base, pv, p_ev=None, p_cool=None, p_charge=None, p_discharge=None) -> np.ndarray:
    """Site demand minus generation per slot (kW); positive = must import. Missing devices count as 0."""
    zero = np.zeros(SLOTS)
    parts = [as_profile(x, name) if x is not None else zero
             for x, name in ((p_ev, "p_ev"), (p_cool, "p_cool"), (p_charge, "p_charge"), (p_discharge, "p_discharge"))]
    ev, cool, charge, discharge = parts
    return as_profile(base, "base") + ev + cool + charge - discharge - as_profile(pv, "pv")


def grid_flows(net_kw) -> tuple[np.ndarray, np.ndarray]:
    """(import, export) in kW: the grid absorbs any difference; never both in the same slot."""
    net = as_profile(net_kw, "net_kw")
    return np.clip(net, 0, None), np.clip(-net, 0, None)


def check_import_limit(params: GridParams, grid_import_kw) -> list[str]:
    """Slots where import exceeds the sanctioned load."""
    g = as_profile(grid_import_kw, "grid_import_kw")
    return [f"grid slot {t}: import {g[t]:.3f} kW > limit {params.import_limit_kw} kW"
            for t in range(SLOTS) if g[t] > params.import_limit_kw + TOL]


def daily_cost(price, grid_import_kw, grid_export_kw, export_price: float) -> float:
    """Sum of (buy price x import - export price x export) x 0.25 h."""
    p, g_imp, g_exp = as_profile(price, "price"), as_profile(grid_import_kw, "import"), as_profile(grid_export_kw, "export")
    return float(((p * g_imp - export_price * g_exp) * DT_H).sum())


def peak_import_kw(grid_import_kw) -> float:
    """Highest import in any slot (kW)."""
    return float(as_profile(grid_import_kw, "grid_import_kw").max())


def self_consumption_pct(pv_kw, grid_export_kw) -> float:
    """Share of PV energy used on site (directly or via storage) = (PV - export) / PV, in %; NaN without PV."""
    pv_kwh = float(as_profile(pv_kw, "pv").sum() * DT_H)
    export_kwh = float(as_profile(grid_export_kw, "export").sum() * DT_H)
    if pv_kwh <= TOL:
        return float("nan")
    return max(pv_kwh - export_kwh, 0.0) / pv_kwh * 100
