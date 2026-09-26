# Machine learning

The platform combines transaction classification and volatility forecasting.
Both workflows expose their data sources and keep evaluation separate from
serving behavior.

| Workflow | In the application |
|---|---|
| [Transaction classification](transaction-classification.md) | Suggests editable categories for transactions and bank-feed activity |
| [Volatility forecasting](volatility-forecasting.md) | Shows a source-labeled volatility estimate for an instrument |

## Results at a glance

| Evaluation | Key result |
|---|---|
| Earlier rules + TF-IDF policy, 252 English/German challenge cases | 69.8% accuracy; 60.7% automatically classified, with 96.1% accuracy among those cases |
| Multilingual E5, 44 in-scope descriptions in the frozen manual test | 95.5% accuracy; 95.4% macro-F1 |
| Current bank-feed service, 1,500 generated transactions | 58.6% automatically classified; all 879 accepted labels matched the generator |
| XGBoost volatility model, 24,100 historical test forecasts | MAE 0.0690, RMSE 0.1076, QLIKE 0.3164, bias −0.0194; Ridge MAE was 0.0699 |

Accuracy measures correct categories across evaluated examples. Automatic
coverage measures how often the service assigns a category without review;
accuracy among accepted cases measures correctness only within that subset.
Macro-F1 averages each category's F1 score, balancing precision and recall
while giving categories equal weight. Forecast MAE is the average absolute
error in annualized volatility units: 0.0690 is about 6.9 percentage points.
RMSE emphasizes larger forecast errors. QLIKE compares predicted and realized
variance; bias is average prediction minus realization. Lower MAE, RMSE, and
QLIKE are better, while bias closer to zero is better.
These evaluations use different datasets and should not be compared as one
leaderboard.

The [category definitions](transaction_categories.md) explain the labels.
The classification datasets are included and use synthetic or curated text.
The bank simulation checks the application against its own generator, so its
match rate is not a measure of accuracy on real bank data. The market study's
licensed SIP prices and trained artifact are not included; its figures come
from versioned evaluation summaries. See the [aggregate metric tables](evaluation-results.md)
for the full comparison, the [brief experiment history](experiment-history.md)
for earlier decisions, and the [evaluation commands](reproducibility.md) for
the steps and underlying evidence.
