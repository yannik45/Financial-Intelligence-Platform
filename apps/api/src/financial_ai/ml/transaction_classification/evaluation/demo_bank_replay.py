"""Replay the current classifier on fixed synthetic bank-feed scenarios."""

import json

from financial_ai.demo_bank_feed import generate_demo_bank_feed
from financial_ai.ml.transaction_classification.core.category_service import (
    get_transaction_classifier,
)
from financial_ai.ml.transaction_classification.core.contracts import (
    ClassificationInputSource,
)


def run() -> None:
    classifier = get_transaction_classifier()
    status = classifier.status()
    if status.mode != "agreement_v2":
        raise RuntimeError("The semantic agreement policy must be ready for this replay")

    items = [
        item
        for seed in range(100)
        for item in generate_demo_bank_feed(seed=seed, year=2026, month=8, variable_count=12)
    ]
    decisions = classifier.classify_many(
        [(item.description, item.amount, item.counterparty) for item in items],
        input_source=ClassificationInputSource.BANK_FEED,
    )
    accepted = [
        (item, decision)
        for item, decision in zip(items, decisions, strict=True)
        if not decision.needs_review and decision.category is not None
    ]
    correct = sum(
        decision.category.casefold() == item.expected_category.casefold()
        for item, decision in accepted
    )
    print(
        json.dumps(
            {
                "scenario": "synthetic_demo_bank_100_seeds_v1",
                "rows": len(items),
                "accepted": len(accepted),
                "correct_accepted": correct,
                "automatic_coverage": len(accepted) / len(items),
                "accepted_accuracy": correct / len(accepted) if accepted else None,
                "tfidf_model_version": status.tfidf_model_version,
                "semantic_model_version": status.semantic_model_version,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    run()
