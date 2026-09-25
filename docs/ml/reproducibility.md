# Reproducing the ML evidence

Use Python 3.12 and the locked environment. Generated datasets, reports, and
model artifacts go under ignored `data/runtime/`; they do not change the
committed evaluation records.

```powershell
uv sync --locked --all-groups
uv run pytest apps/api/tests
uv sync --locked --all-groups --extra semantic
uv run --extra semantic financial-ai-bootstrap-category-model
uv run --extra semantic financial-ai-evaluate-text-classification
uv run --extra semantic financial-ai-evaluate-semantic-final-test
uv run --extra semantic python -m financial_ai.ml.transaction_classification.evaluation.multilingual_final_evaluation
uv run --extra semantic python -m financial_ai.ml.transaction_classification.evaluation.demo_bank_replay
```

The semantic extra downloads the pinned multilingual E5 encoder on its first
run. Without it, the application still runs in an explicitly degraded TF-IDF
mode, but the semantic evaluations cannot be reproduced. `uv run --extra semantic`
keeps that optional dependency set active for each evaluation command.

## Checks run on 2026-09-25

| Check | Outcome |
|---|---|
| Backend test suite | Passed after fixing two Windows line-ending checksum checks |
| `financial-ai-evaluate-text-classification` | Reproduced the 252-case lexical/rules challenge: 69.8% overall accuracy, 60.7% automatic coverage, 96.1% accuracy among accepted cases |
| `financial-ai-evaluate-semantic-final-test` | Reproduced the committed 44-case in-scope manual result: 95.45% accuracy |
| `python -m financial_ai.ml.transaction_classification.evaluation.multilingual_final_evaluation` | Reproduced the historical controlled English/German final report |
| `python -m financial_ai.ml.transaction_classification.evaluation.demo_bank_replay` | Current service accepted 879 of 1,500 fixed generated bank transactions, all matching generator labels |
| `financial-ai-evaluate-market-final-test` | Could not run: the versioned historical SIP dataset is not in this checkout |

The older [bank-policy selection record](../../data/evaluation/transaction_categories/classification_v2_bank_policy_selection.json)
reports 62.8% coverage and 93.7% accepted accuracy for a pre-integration
experiment. It is preserved as a decision record, not a current-service metric.
The current replay above is the relevant demo check. Both use synthetic data.

## Historical market experiment

The committed [selection](../../data/evaluation/market_forecast/inner_cv_v1.summary.json),
[validation](../../data/evaluation/market_forecast/outer_validation_v1.summary.json),
and [final-test](../../data/evaluation/market_forecast/final_test_v1.summary.json)
summaries have a checksum-linked evaluation chain. The automated evidence test
checks that chain, but it cannot recompute predictions or metrics without the
raw bars. A rerun requires Alpaca credentials with historical SIP access, the
pinned 50-symbol universe, and rebuilding the dataset and evaluation reports in
order. The acquisition and build commands live in the
[`data` modules](../../apps/api/src/financial_ai/ml/market_forecast/data/);
the final command is:

```powershell
uv run financial-ai-evaluate-market-final-test `
  --dataset-version us-large-cap-volatility-v1 `
  --validation-version us-large-cap-xgboost-v1 `
  --test-version us-large-cap-final-v1
```

The published market numbers are therefore **recorded results, not independently
rerun results from this checkout**. The Docker demo and the backend test suite
exercise the forecast contract and EWMA path; neither verifies those historical
XGBoost metrics.
