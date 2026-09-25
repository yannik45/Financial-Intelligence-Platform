# Transaction classification

The transaction form suggests a category from a description, optional
counterparty, and the sign of the cash flow. A person can edit the suggestion.
The backend classifies again when saving and records the prediction, final label,
model versions, and review state. Amount magnitude is not a model feature.

## How a suggestion is made

```text
Text + inflow/outflow direction
  -> small English/German rules for clear cases
  -> bank-feed outflow: TF-IDF and multilingual E5 must agree to auto-accept
  -> manual outflow: editable E5 suggestion
  -> unsupported or unclear input: review
```

The lexical model uses character TF-IDF and logistic regression. The semantic
model uses a frozen multilingual E5 encoder with a logistic-regression head.
If the semantic artifact is unavailable, the API reports a degraded state and
uses a more conservative lexical fallback. Scores are ranking signals, not
calibrated probabilities. The active behavior lives in
[`category_service.py`](../../apps/api/src/financial_ai/ml/transaction_classification/core/category_service.py).

## Evidence and its limits

| Evaluation | Result | What it tells us |
|---|---|---|
| 252-case English/German product challenge, rules + lexical model | 69.8% overall accuracy; 60.7% automatically accepted at 96.1% accuracy among accepted cases | Reproduced from the committed challenge; this tests the earlier lexical policy, not the current E5 agreement policy |
| 1,500 seeded synthetic bank transactions, current E5/TF-IDF service | 879 auto-accepted (58.6%); all matched generator labels | Replayed against the current code and artifacts; these generated scenarios are not an independent test |
| 44 in-scope, manually curated short descriptions, E5 | 95.5% category accuracy | Small frozen test; it does not measure broad free-form usage |

Training text and these evaluation sets are synthetic or curated. Merchant,
phrase, and template groups are separated where the dataset supports it, but
none of the scores establish accuracy on real bank data. The 252-case challenge
was authored alongside the application. The bank simulation is useful for
finding failures, but its generator and classifier share design assumptions.
The [verification guide](reproducibility.md) separates rerun results from
versioned records.

An older bank-policy selection record reports different coverage and accuracy.
It predates serving integration and should not be used as a current-service
metric. The current seeded replay is executable from the repository.

## Feedback lifecycle

Corrections are stored as feedback; they never retrain a live model. An offline
command exports explicitly reviewed labels, a human reviews the text, and a
candidate model is trained in isolation. Promotion requires fixed evaluation
gates and an explicit command; the previous artifact is archived. The current
candidate path updates only the lexical expense model. Exported free text can
still be sensitive even though identifiers and amount magnitude are omitted.

The classifier has 12 learned expense labels. Six additional product labels use
high-signal rules or review. See the [compact category taxonomy](transaction_categories.md)
for their boundaries. There is no authentication, so the demo must not contain
real personal or account data.
