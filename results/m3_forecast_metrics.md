# M3 forecast accuracy

MAE/RMSE/bias in kW per 15-min slot; nMAE = MAE / mean actual (all slots incl. night).

## PV power — test (273 days)

| Season | Model | MAE kW | RMSE kW | nMAE % | Bias kW |
|---|---|---|---|---|---|
| all | Persistence (yesterday) | 0.095 | 0.267 | 9.8 | -0.001 |
| all | Weather-forecast physics | 0.068 | 0.203 | 7.0 | +0.012 |
| all | LightGBM | 0.078 | 0.210 | 8.1 | +0.023 |
| monsoon | Persistence (yesterday) | 0.167 | 0.386 | 18.6 | +0.002 |
| monsoon | Weather-forecast physics | 0.126 | 0.295 | 14.0 | +0.016 |
| monsoon | LightGBM | 0.135 | 0.304 | 15.0 | +0.061 |
| dry | Persistence (yesterday) | 0.036 | 0.093 | 3.6 | -0.003 |
| dry | Weather-forecast physics | 0.021 | 0.065 | 2.1 | +0.009 |
| dry | LightGBM | 0.032 | 0.068 | 3.1 | -0.008 |

## PV power — val (184 days)

| Season | Model | MAE kW | RMSE kW | nMAE % | Bias kW |
|---|---|---|---|---|---|
| all | Persistence (yesterday) | 0.137 | 0.352 | 17.5 | +0.001 |
| all | Weather-forecast physics | 0.145 | 0.361 | 18.5 | -0.111 |
| all | LightGBM | 0.108 | 0.255 | 13.9 | -0.010 |
| monsoon | Persistence (yesterday) | 0.215 | 0.456 | 27.8 | +0.001 |
| monsoon | Weather-forecast physics | 0.259 | 0.498 | 33.5 | -0.222 |
| monsoon | LightGBM | 0.176 | 0.341 | 22.8 | -0.025 |
| dry | Persistence (yesterday) | 0.058 | 0.202 | 7.4 | +0.001 |
| dry | Weather-forecast physics | 0.030 | 0.113 | 3.8 | -0.000 |
| dry | LightGBM | 0.040 | 0.119 | 5.1 | +0.006 |

## Base load — test (273 days)

| Season | Model | MAE kW | RMSE kW | nMAE % | Bias kW |
|---|---|---|---|---|---|
| all | Persistence (yesterday) | 0.091 | 0.126 | 20.6 | -0.000 |
| all | Same day last week | 0.074 | 0.103 | 16.8 | -0.000 |
| all | LightGBM | 0.053 | 0.073 | 12.0 | -0.000 |
| monsoon | Persistence (yesterday) | 0.091 | 0.127 | 20.7 | +0.001 |
| monsoon | Same day last week | 0.074 | 0.103 | 16.8 | -0.000 |
| monsoon | LightGBM | 0.053 | 0.073 | 12.0 | +0.000 |
| dry | Persistence (yesterday) | 0.090 | 0.125 | 20.5 | -0.001 |
| dry | Same day last week | 0.074 | 0.102 | 16.8 | -0.000 |
| dry | LightGBM | 0.053 | 0.073 | 12.0 | -0.000 |

## Base load — val (184 days)

| Season | Model | MAE kW | RMSE kW | nMAE % | Bias kW |
|---|---|---|---|---|---|
| all | Persistence (yesterday) | 0.090 | 0.125 | 20.5 | +0.000 |
| all | Same day last week | 0.074 | 0.103 | 16.8 | +0.000 |
| all | LightGBM | 0.052 | 0.073 | 11.9 | +0.001 |
| monsoon | Persistence (yesterday) | 0.091 | 0.126 | 20.8 | +0.000 |
| monsoon | Same day last week | 0.074 | 0.103 | 16.9 | +0.000 |
| monsoon | LightGBM | 0.053 | 0.074 | 12.1 | +0.002 |
| dry | Persistence (yesterday) | 0.089 | 0.123 | 20.3 | -0.000 |
| dry | Same day last week | 0.074 | 0.102 | 16.8 | +0.000 |
| dry | LightGBM | 0.052 | 0.072 | 11.8 | -0.000 |
