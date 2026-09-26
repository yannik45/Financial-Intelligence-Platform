# Experiment history

This is a short record of how the two ML workflows reached their current
design. Earlier results are retained as development evidence, not mixed into
current-service performance. [Evaluation results](evaluation-results.md)
collect the aggregate metrics.

| Stage | Decision and reason |
|---|---|
| External dataset → Controlled generators | An initial proof-of-concept used the public `DoDataThings` synthetic dataset (~25k rows). It was superseded by custom English and German generators because it was English-only and suffered from merchant/template leakage across random splits. |
| English and German lexical baselines | Controlled, grouped synthetic splits exposed a validation-to-test gap. The bilingual character TF-IDF model was retained as the single lexical reference; language-specific models remained comparison baselines. |
| Product challenge v1 → v2 | The frozen challenge was versioned again after fixing dividend cash-flow direction and adding counterparty coverage. Its changed numbers are an evaluation correction, not a model gain. |
| Semantic classifier | Multilingual E5 transferred better to short manual descriptions, while TF-IDF was stronger on controlled bank-feed validation. After high-signal rules, the selected service asks both models to agree for automatic bank-feed labels and offers an editable E5 suggestion for manual entry. |
| Feature fusion | Combining TF-IDF and E5 features improved controlled bank validation but reduced manual accuracy and conservative coverage on the generated bank simulation. It was rejected before the frozen manual test. |
| Market baselines → XGBoost | Constant, persistence, EWMA, and Ridge references preceded purged XGBoost selection. XGBoost led MAE, RMSE, and QLIKE on the historical validation and final periods; the final test closed selection for this model version. |
| Current application | The historical XGBoost artifact is optional. Included synthetic prices use a separately labeled EWMA estimate; classification evaluations and the current bank-service simulation are documented separately. |

The longer original notes are preserved in Git history at commit `ade6d9a`.
For example, `git show ade6d9a:docs/ml/transaction_classification_v2.md` and
`git show ade6d9a:docs/ml/market_volatility_boosting.md` retrieve the detailed
selection narratives. Those notes sometimes describe pre-integration behavior;
the current workflow guides describe what the application serves now.
