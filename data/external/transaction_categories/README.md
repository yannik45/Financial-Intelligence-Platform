# Optional source for the early categorization baseline

The early classifier experiment used the synthetic
[`DoDataThings/us-bank-transaction-categories-v2`](https://huggingface.co/datasets/DoDataThings/us-bank-transaction-categories-v2)
dataset. It is not customer data and is not required to run the application or
the current frozen evaluations.

The raw CSV is not committed. To download the pinned, checksum-verified copy
into ignored `data/runtime/`, run from the repository root:

```powershell
uv run python -m financial_ai.ml.category_dataset
```

The destination is `data/runtime/ml/transaction_categories/transactions-synthetic.csv`.
See `metadata.json` in this directory for source and integrity details.
