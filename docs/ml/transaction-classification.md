# Transaction classification

The transaction form suggests a category from a description, optional
counterparty, and the sign of the cash flow. Users can edit the suggestion.
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

## Data foundations and dataset roles

The classification workflow evolved from an early external baseline into
controlled synthetic generators, and evaluates bank feeds and manual entries on
dedicated benchmarks:

| Dataset | Size | Language | Role / Purpose | Evaluated policy |
|---|---|---|---|---|
| `DoDataThings` *(Legacy)* | ~25k rows | EN | Historical initial baseline (superseded) | Early TF-IDF |
| Controlled generators | 16,500 rows | EN + DE | Active training data with strict group holdouts | Bilingual TF-IDF + E5 head |
| [Product challenge v2](../../data/evaluation/transaction_categories/text_classification_challenge_v2.csv) | 252 cases | EN + DE | Frozen challenge benchmark across difficulty tiers | Rules + TF-IDF with abstention |
| [Manual test](../../data/evaluation/transaction_categories/classification_v2_manual_test.json) | 44 (+4) cases | EN + DE | Frozen benchmark of short user descriptions | Multilingual E5 semantic head |
| Bank feed replay | 1,500 rows | EN + DE | Runtime integration check on simulated feed | Full agreement policy (Rules + TF-IDF + E5) |

### Why custom generators replaced the external dataset

The initial proof-of-concept used the public synthetic dataset
[`DoDataThings/us-bank-transaction-categories-v2`](../../data/external/transaction_categories/README.md).
While helpful for early pipeline testing, it was English-only and had merchant
and template leakage across naive splits, causing models to memorize merchant
names rather than general category signals. It also lacked German banking
structures (SEPA, Überweisung, Lastschrift, Kartenzahlung).

To create reproducible, leakage-free benchmarks, custom generators
([`english_training_generator_v1`](../../apps/api/src/financial_ai/ml/transaction_classification/data/english_training_generator_v1.py)
and [`german_training_generator_v2`](../../apps/api/src/financial_ai/ml/transaction_classification/data/german_training_generator_v2.py))
were developed. They enforce strict group holdouts: merchant groups, format
templates, and detail phrases never overlap between train, validation, and test
splits. The active bilingual classifier is bootstrapped from 16,500 balanced rows
produced by these generators.

## Evaluation

The frozen [manual test record](../../data/evaluation/transaction_categories/classification_v2_manual_test.json)
contains 48 curated short descriptions: 44 with a supported expense label and
four intentionally out of scope. The multilingual E5 classifier produced:

| Metric on the 44 in-scope cases | Result |
|---|---:|
| Category accuracy | 95.5% (42/44) |
| Macro-F1 | 95.4% |
| Automatic coverage | 97.7% (43/44) |
| Accuracy among automatically accepted cases | 95.3% (41/43) |

All four out-of-scope examples were sent to review. Accuracy was 90.9% on
22 known-concept/new-phrase cases and 100% on 22 novel-concept cases; those
small slices are descriptive. Macro-F1 averages the F1
score across expense categories, so frequent labels do not dominate it.
Automatic coverage is the share assigned without review; accepted accuracy
measures correctness within that share. This is a small, curated test of short
descriptions, not a measurement on real bank transactions.

The earlier rules-plus-TF-IDF product policy was evaluated on the frozen
[252-case English/German challenge](../../data/evaluation/transaction_categories/text_classification_challenge_v2.csv).
Its comparison explains why rules and lexical predictions were combined:

| Policy | Overall accuracy | Macro-F1 | Automatic coverage | Accepted accuracy |
|---|---:|---:|---:|---:|
| Rules only | 32.1% | 46.1% | 33.7% | 95.3% |
| TF-IDF only | 57.1% | 47.6% | 43.3% | 96.3% |
| Rules + TF-IDF | 69.8% | 68.4% | 60.7% | 96.1% |

Review cases count as unclassified in overall accuracy. This challenge tests
the earlier lexical policy, not the current TF-IDF/E5 agreement policy.
The [aggregate metric tables](evaluation-results.md) also show prediction
coverage, review rate, rule coverage, expense-only results, and language and
difficulty slices.

On a separate [model-selection validation set](../../data/evaluation/transaction_categories/classification_v2_model_selection.json),
the two models performed differently across inputs:

| Candidate | Bank accuracy | Bank coverage | Manual accuracy | Manual coverage |
|---|---:|---:|---:|---:|
| TF-IDF | 88.7% | 96.5% | 56.8% | 50.0% |
| E5 | 79.3% | 80.5% | 95.5% | 100.0% |

The bank slice has 2,750 examples; the short-description slice has 44. This
trade-off motivated agreement for bank feeds and E5 suggestions for manual
entry. These are validation results, not additional final-test results.

For the current serving policy, a check of 1,500 seeded synthetic bank
transactions automatically assigned 879 (58.6%); all 879 labels matched the
generator. The simulation and classifier share assumptions, so this checks
serving behavior rather than independent accuracy. An older
[bank-policy selection record](../../data/evaluation/transaction_categories/classification_v2_bank_policy_selection.json)
reports different figures from before serving integration; the current check
is the relevant service measurement.

Training and evaluation text are synthetic or curated. Merchant, phrase, and
template groups are separated where the datasets support it, but these
results do not establish accuracy on real bank data. The
[evaluation commands](reproducibility.md) show how to generate the reports.

## Feedback lifecycle

Corrections are stored as feedback; they never retrain a live model. An offline
command exports explicitly reviewed labels, a human reviews the text, and a
candidate model is trained in isolation. Promotion requires fixed evaluation
gates and an explicit command; the previous artifact is archived. The current
candidate path updates only the lexical expense model. Exported free text can
still be sensitive even though identifiers and amount magnitude are omitted.

The classifier has 12 learned expense labels. Six additional product labels use
high-signal rules or review. See the [category taxonomy](transaction_categories.md)
for their boundaries. The current application has no authentication; use
sample data rather than personal or account data.
