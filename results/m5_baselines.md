# M5 baselines — 7 test days from 2026-05-04

Settled on actual data. Money in INR per day (placeholder tariff). Total = electricity + battery wear + comfort penalty + EV-shortfall penalty.

| System | Total cost | Electricity | Battery wear | Discomfort °C·h | EV short kWh | Peak kW | Self-consumption % | Violation days |
|---|---|---|---|---|---|---|---|---|
| S1 rules | 627.87 | 153.11 | 28.16 | 8.93 | 0.00 | 6.40 | 67.1 | 0/7 |
| S2 MILP (pv=lgbm) | 143.98 | 104.88 | 22.63 | 0.33 | 0.00 | 1.95 | 95.5 | 0/7 |
| S2 MILP (pv=physics) | 144.33 | 104.33 | 23.52 | 0.33 | 0.00 | 1.95 | 96.0 | 0/7 |
| S5 oracle | 124.86 | 101.03 | 23.52 | 0.01 | 0.00 | 1.86 | 98.6 | 0/7 |

## Acceptance

- Oracle violation days: 0
- Oracle ≤ every S2 (mean total cost): True
- S2 MILP (pv=lgbm) ≤ S1 (mean total cost): True
- S2 MILP (pv=physics) ≤ S1 (mean total cost): True
