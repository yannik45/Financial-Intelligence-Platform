# Volatility forecasting

The forecasting workflow estimates the annualized volatility of the *next 20
trading days* for US equities. Volatility describes the size of price movements,
not their direction or a probability of loss.

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
final test. The [validation record](../../data/evaluation/market_forecast/outer_validation_v1.summary.json)
contains 24,050 forecasts from 2022-01-03 through 2023-11-30:

| Model | MAE | RMSE | QLIKE |
|---|---:|---:|---:|
| EWMA | 0.0738 | 0.1064 | 0.2647 |
| Ridge | 0.0667 | 0.1034 | 0.2747 |
| XGBoost | 0.0649 | 0.0979 | 0.2376 |

The [final-test record](../../data/evaluation/market_forecast/final_test_v1.summary.json)
contains 24,100 forecasts from 2024-01-02 through 2025-12-02:

| Model | MAE | RMSE | QLIKE | Bias |
|---|---:|---:|---:|---:|
| EWMA | 0.0840 | 0.1229 | 0.3644 | +0.0031 |
| Ridge | 0.0699 | 0.1118 | 0.3517 | −0.0262 |
| XGBoost | 0.0690 | 0.1076 | 0.3164 | −0.0194 |

Lower MAE, RMSE, and QLIKE are better. MAE is the average absolute gap between
predicted and realized volatility; RMSE gives larger misses more weight. Both
are in annualized-volatility units, so 0.0690 MAE is about 6.9 percentage
points. QLIKE compares predicted and realized *variance* using the average of
`r − ln(r) − 1`, where `r = realized² / predicted²`; it is dimensionless. Bias
is average prediction minus realization, so a negative value means
underprediction.

On the final test, XGBoost reduced MAE by 17.8% versus EWMA and 1.3% versus
Ridge; its RMSE and QLIKE were 3.8% and 10.0% lower than Ridge's. Its MAE rose
from 0.0590 in 2024 to 0.0800 in 2025, and it tended to underestimate
high-volatility cases.
Adjacent 20-day targets overlap, and the universe excludes companies that did
not survive to selection. These results describe this historical sample, not
expected accuracy for arbitrary instruments or market regimes. The
[aggregate metric tables](evaluation-results.md) include model selection and
diagnostic slices.

The aggregate reports are versioned and checksum-linked. The licensed SIP
bars used to calculate these metrics are not included in the repository.

## What runs in the application

Instruments using the included synthetic prices show a labeled close-price
EWMA estimate. That fixed series ends on 2026-06-30; later observations are
marked stale. For an external instrument, the API uses a checksum-verified
XGBoost artifact when installed and a labeled EWMA estimate otherwise.
External inference often uses Alpaca IEX while the study used SIP; the API
reports the feed difference. The included price series and historical study
therefore use different data sources and forecast methods.

The licensed raw snapshot, derived training table, and deployment artifact are
not committed. The [evaluation commands](reproducibility.md) explain the data
and access needed to calculate the historical metrics. No real orders are
placed from a forecast.
