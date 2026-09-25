# Volatility forecasting

This experiment estimates the annualized volatility of the *next 20 trading
days* for US equities. Volatility describes the size of price movements, not
their direction or a probability of loss.

## Experiment design

The historical study used daily Alpaca SIP open, high, low, close, adjusted
close, and volume observations for a pinned set of 50 US large-cap survivors.
Ten features use only information available by each forecast date: recent
returns, volatility, momentum, intraday range, and relative volume. The target
uses the following 20 trading days. Splits are chronological: 2016-2021 for
training, 2022-2023 for validation, and 2024-2025 for one final test. Twenty
observations are purged at split boundaries so training targets cannot reach
into a later period.

The study compared a transparent exponentially weighted moving average (EWMA),
Ridge regression, and a selected XGBoost model. Selection happened before the
final test. The compact, checksum-linked [final-test record](../../data/evaluation/market_forecast/final_test_v1.summary.json)
reports:

| Model | Final-test mean absolute error |
|---|---:|
| EWMA | 0.0840 |
| Ridge | 0.0699 |
| XGBoost | 0.0690 |

The error is in annualized-volatility units: 0.069 is about 6.9 percentage
points. XGBoost improved on Ridge by about 1.3% on this metric. It still tended
to underestimate high-volatility cases. Adjacent targets overlap, and the
universe excludes companies that did not survive to selection. These results
are evidence for this historical sample, not proof of reliable forecasts for
arbitrary instruments or market regimes.

## What runs in the application

A fresh Docker checkout has no historical SIP dataset or trained XGBoost
artifact. Demo instruments have synthetic closing prices only, so their panel
uses a labeled close-price EWMA reference. The fixed demo series ends on
2026-06-30; later observations are marked stale and shown as historical estimates.
For an external instrument, the API uses the checksum-verified XGBoost artifact
if one is installed, and a labeled EWMA reference otherwise. External inference
often uses Alpaca IEX while the study used SIP; the API reports that feed
difference. The evaluated model and the Docker demo therefore represent
different evidence and data sources.

The licensed raw snapshot, derived training table, and deployment artifact are
not committed. The [verification guide](reproducibility.md) explains which
checks can run from this repository and what is needed to rerun the historical
test. No real orders are placed from a forecast.
