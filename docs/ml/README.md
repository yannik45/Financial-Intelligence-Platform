# Machine learning in this project

Two ML workflows support the portfolio application. They are experiments with
explicit review and provenance, not production models trained on customer data.

| Workflow | What a reviewer can try | What has been evaluated |
|---|---|---|
| [Transaction classification](transaction-classification.md) | Generate a synthetic bank feed, inspect category suggestions, and correct them | Rules, character TF-IDF, and a multilingual semantic model on synthetic English/German data |
| [Volatility forecasting](volatility-forecasting.md) | Open a forecast for a demo instrument | An EWMA reference runs on synthetic demo prices; a separate XGBoost experiment used historical US equities |

The [category definitions](transaction_categories.md) explain the labels. The
[verification guide](reproducibility.md) lists commands, evidence files, and
which results can be rerun from a clean checkout.

The distinction between *recorded* and *reproduced* results matters here. The
classifier's small synthetic and curated benchmarks can be regenerated locally. The market
experiment's aggregate reports are versioned, but its licensed historical SIP
snapshot and trained artifact are not committed. Running the Docker demo does
not reproduce the XGBoost test or serve that model by default.
