import json
from pathlib import Path

import pandas as pd
import pytest
from financial_ai.ml.transaction_classification.core.category_service import (
    TransactionClassifier,
)
from financial_ai.ml.transaction_classification.evaluation.text_classification_evaluation import (
    ABSTENTION_LABEL,
    evaluate_text_classification_strategies,
    write_evaluation_report,
)
from financial_ai.ml.transaction_classification.modeling.category_artifact import (
    LoadedCategoryModel,
    ModelMetadata,
)
from financial_ai.ml.transaction_classification.modeling.category_model import (
    train_tfidf_category_classifier,
)


@pytest.fixture
def loaded_category_model() -> LoadedCategoryModel:
    training_data = pd.DataFrame(
        {
            "description": [
                "supermarket food",
                "supermarket groceries",
                "Lebensmittel Markt",
                "Lebensmittel Supermarkt",
                "restaurant dinner",
                "restaurant lunch",
                "Restaurant Abendessen",
                "Restaurant Mittagessen",
            ],
            "target_category": ["groceries"] * 4 + ["dining"] * 4,
        }
    )
    model = train_tfidf_category_classifier(training_data)
    metadata = ModelMetadata(
        model_version="evaluation-test-model-v1",
        taxonomy_version="transaction-categories-v1",
        generator_version="test",
        created_at="2026-07-31T00:00:00+00:00",
        training_rows=len(training_data),
        languages=("en", "de"),
        training_source_sha256={"test": "abc"},
        artifact_sha256="def",
    )
    return LoadedCategoryModel(model=model, metadata=metadata)


def _small_challenge() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("Monthly salary", 100, "income", "en", "easy", False),
            ("Monatliches Gehalt", 100, "income", "de", "medium", False),
            ("Corner kiosk provisions", -20, "groceries", "en", "easy", False),
            ("Lebensmittel vom Markt", -20, "groceries", "de", "medium", False),
            ("Restaurant dinner", -20, "dining", "en", "hard", True),
            ("Abendessen Restaurant", -20, "dining", "de", "hard", True),
        ],
        columns=[
            "description",
            "amount",
            "expected_category",
            "language",
            "difficulty",
            "ambiguity",
        ],
    ).assign(counterparty="")


def test_evaluation_compares_all_strategies_and_slices(loaded_category_model, monkeypatch):
    def unexpected_semantic_load(self):
        raise AssertionError("The frozen lexical evaluation must not load E5")

    monkeypatch.setattr(TransactionClassifier, "_get_semantic_model", unexpected_semantic_load)
    evaluations = evaluate_text_classification_strategies(
        _small_challenge(), loaded_category_model, review_threshold=0.01
    )

    assert [evaluation.strategy for evaluation in evaluations] == [
        "text_rules_only",
        "tfidf_only",
        "hybrid",
    ]
    hybrid = evaluations[2]
    assert hybrid.full_system.rows == 6
    assert hybrid.expense_only.rows == 4
    assert set(hybrid.by_language) == {"de", "en"}
    assert set(hybrid.by_difficulty) == {"easy", "hard", "medium"}
    assert set(hybrid.by_ambiguity) == {"false", "true"}
    assert hybrid.full_system.rule_coverage > 0


def test_rule_only_records_abstentions(loaded_category_model):
    evaluations = evaluate_text_classification_strategies(_small_challenge(), loaded_category_model)
    rule_only = evaluations[0].full_system

    assert ABSTENTION_LABEL in rule_only.confusion_labels
    assert rule_only.review_rate > 0
    assert rule_only.prediction_coverage < 1


def test_report_is_machine_readable(tmp_path: Path, loaded_category_model):
    evaluations = evaluate_text_classification_strategies(
        _small_challenge(), loaded_category_model, review_threshold=0.01
    )
    destination = tmp_path / "report.json"

    write_evaluation_report(
        evaluations,
        destination,
        review_threshold=0.01,
        model_version="evaluation-test-model-v1",
        model_artifact_sha256="abc123",
    )
    report = json.loads(destination.read_text(encoding="utf-8"))

    assert report["evaluation_version"] == "text-classification-evaluation-v2"
    assert report["review_threshold"] == 0.01
    assert report["model_version"] == "evaluation-test-model-v1"
    assert report["model_artifact_sha256"] == "abc123"
    assert len(report["evaluations"]) == 3
    assert report["evaluations"][2]["strategy"] == "hybrid"
    assert (
        report["evaluations"][2]["full_system"]["rule_coverage"]
        == evaluations[2].full_system.rule_coverage
    )
