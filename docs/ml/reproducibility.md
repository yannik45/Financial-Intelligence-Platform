# Run the ML evaluations

Use Python 3.12 and the locked environment. Generated datasets, reports, and
model artifacts go under ignored `data/runtime/`.

```powershell
uv sync --locked --all-groups
uv run pytest apps/api/tests
uv sync --locked --all-groups --extra semantic
uv run --extra semantic financial-ai-bootstrap-category-model
uv run --extra semantic financial-ai-evaluate-text-classification
uv run --extra semantic financial-ai-evaluate-semantic-classification
uv run --extra semantic financial-ai-diagnose-classification-validation
uv run --extra semantic financial-ai-evaluate-classification-fusion
uv run --extra semantic financial-ai-evaluate-semantic-final-test
uv run --extra semantic python -m financial_ai.ml.transaction_classification.evaluation.multilingual_final_evaluation
uv run --extra semantic python -m financial_ai.ml.transaction_classification.evaluation.demo_bank_replay
```

The semantic extra downloads the pinned multilingual E5 encoder on its first
run. Without it, the application still runs in an explicitly degraded TF-IDF
mode, but the semantic evaluations require the encoder. `uv run --extra semantic`
keeps that optional dependency set active for each evaluation command.

## Classifier data and results

The classifier datasets are included. The commands above produce the 252-case
lexical/rules result (69.8% accuracy, 60.7% automatic coverage, 96.1% accepted
accuracy), semantic validation and diagnostics, the 44-case manual semantic
result (95.45% accuracy), and the controlled English/German result. The bank-feed
simulation exercises current serving behavior on 1,500 generated transactions:
879 were accepted, and all accepted labels matched the generator. Full metrics
and cohort definitions are in [Evaluation results](evaluation-results.md).

The older [bank-policy selection summary](../../data/evaluation/transaction_categories/classification_v2_bank_policy_selection.json)
describes a pre-integration experiment on generated scenarios. Its 62.8%
coverage and 93.7% accepted accuracy should not be read as current service
performance.

## Market data requirement

The committed [selection](../../data/evaluation/market_forecast/inner_cv_v1.summary.json),
[validation](../../data/evaluation/market_forecast/outer_validation_v1.summary.json),
and [final-test](../../data/evaluation/market_forecast/final_test_v1.summary.json)
summaries have a checksum-linked evaluation chain. The automated evidence test
checks that chain. Calculating predictions and metrics requires the source price
bars, which are not committed to git. The commands below use Alpaca API credentials
placed in a local `.env` (`FINANCIAL_AI_ALPACA_API_KEY` and `FINANCIAL_AI_ALPACA_SECRET_KEY`)
to download historical daily bars for the pinned 50-symbol universe:

```powershell
uv run financial-ai-download-market-snapshot `
  --universe-path data/market/market_forecast_universe_v1.json `
  --date-from 2016-01-01 --date-to 2025-12-31 `
  --version us-large-cap-sip-price-v1
uv run financial-ai-build-market-dataset `
  --snapshot-version us-large-cap-sip-price-v1 `
  --dataset-version us-large-cap-volatility-v1
uv run financial-ai-evaluate-market-validation `
  --dataset-version us-large-cap-volatility-v1 `
  --evaluation-version us-large-cap-baselines-v1
uv run financial-ai-select-market-boosting-model `
  --dataset-version us-large-cap-volatility-v1 `
  --selection-version inner-cv-v1
uv run financial-ai-evaluate-market-boosting `
  --dataset-version us-large-cap-volatility-v1 `
  --selection-version inner-cv-v1 `
  --evaluation-version us-large-cap-xgboost-v1
uv run financial-ai-diagnose-market-boosting `
  --dataset-version us-large-cap-volatility-v1 `
  --selection-version inner-cv-v1 `
  --diagnostics-version outer-validation-diagnostics-v1
uv run financial-ai-evaluate-market-final-test `
  --dataset-version us-large-cap-volatility-v1 `
  --validation-version us-large-cap-xgboost-v1 `
  --test-version us-large-cap-final-v1
uv run financial-ai-build-market-forecast-model `
  --dataset-version us-large-cap-volatility-v1
```

The final command refits the selected XGBoost model on all 119,700 labeled rows
(train + validation + test) and outputs the deployable artifact
(`market_volatility_xgboost_v1.ubj` and metadata) to `data/runtime/ml/market_forecast/models/`.

Without the snapshot and dataset, market validation and final-test commands stop
before scoring. The [market metrics](volatility-forecasting.md) come from the versioned
aggregate summaries; their checksum links do not establish the underlying
predictions. The Docker demo and backend tests exercise the forecast contract
and EWMA path, not the historical XGBoost calculations.
