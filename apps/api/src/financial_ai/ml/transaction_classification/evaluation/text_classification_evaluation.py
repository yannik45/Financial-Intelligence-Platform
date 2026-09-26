import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path

import pandas as pd
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score

from financial_ai.ml.transaction_classification.core.categories import ExpenseCategory
from financial_ai.ml.transaction_classification.core.category_service import (
    DEFAULT_REVIEW_THRESHOLD,
    TransactionClassifier,
)
from financial_ai.ml.transaction_classification.core.contracts import ClassificationMethod
from financial_ai.ml.transaction_classification.core.text_classification_rules import (
    match_text_category,
)
from financial_ai.ml.transaction_classification.evaluation.text_classification_challenge import (
    CHALLENGE_VERSION,
    DEFAULT_CHALLENGE_PATH,
    load_text_classification_challenge,
)
from financial_ai.ml.transaction_classification.modeling.category_artifact import (
    DEFAULT_ARTIFACT_PATH,
    LoadedCategoryModel,
    calculate_sha256,
    load_category_model_artifact,
)

DEFAULT_REPORT_PATH = Path(
    "data/runtime/ml/transaction_categories/text_classification_evaluation_v2.json"
)
EVALUATION_VERSION = "text-classification-evaluation-v2"
ABSTENTION_LABEL = "__needs_review__"


@dataclass(frozen=True)
class PredictionRecord:
    expected: str
    predicted: str | None
    language: str
    difficulty: str
    ambiguity: bool
    method: str
    confidence: float | None
    needs_review: bool


@dataclass(frozen=True)
class CategoryResult:
    category: str
    precision: float
    recall: float
    f1: float
    support: int


@dataclass(frozen=True)
class MetricSummary:
    rows: int
    accuracy: float
    macro_f1: float
    prediction_coverage: float
    review_rate: float
    auto_acceptance_rate: float
    selective_accuracy: float | None
    rule_coverage: float
    per_category: tuple[CategoryResult, ...]
    confusion_labels: tuple[str, ...]
    confusion_matrix: tuple[tuple[int, ...], ...]


@dataclass(frozen=True)
class StrategyEvaluation:
    strategy: str
    full_system: MetricSummary
    expense_only: MetricSummary
    by_language: dict[str, MetricSummary]
    by_difficulty: dict[str, MetricSummary]
    by_ambiguity: dict[str, MetricSummary]


def _predict_with_model(
    loaded_model: LoadedCategoryModel,
    text: str,
    amount: Decimal,
    review_threshold: float,
) -> tuple[str | None, str, float | None, bool]:
    if amount > 0:
        return None, ClassificationMethod.NONE.value, None, True
    probabilities = loaded_model.model.predict_proba(pd.Series([text]))[0]
    best_index = int(probabilities.argmax())
    confidence = float(probabilities[best_index])
    return (
        str(loaded_model.model.classes_[best_index]),
        ClassificationMethod.ML.value,
        confidence,
        confidence < review_threshold,
    )


def _records_for_strategy(
    challenge: pd.DataFrame,
    loaded_model: LoadedCategoryModel,
    strategy: str,
    review_threshold: float,
) -> list[PredictionRecord]:
    # Freeze the v1 lexical policy even when a v2 semantic artifact is installed.
    classifier = TransactionClassifier(
        loaded_model, review_threshold=review_threshold, semantic_enabled=False
    )
    records: list[PredictionRecord] = []
    for row in challenge.itertuples(index=False):
        text = " ".join(part for part in (row.description, row.counterparty) if part).strip()
        amount = Decimal(str(row.amount))
        if strategy == "text_rules_only":
            category = match_text_category(text)
            predicted = category.value if category else None
            method = (
                ClassificationMethod.KEYWORD_RULE.value
                if category
                else ClassificationMethod.NONE.value
            )
            confidence = None
            needs_review = category is None
        elif strategy == "tfidf_only":
            predicted, method, confidence, needs_review = _predict_with_model(
                loaded_model,
                text,
                amount,
                review_threshold,
            )
        elif strategy == "hybrid":
            result = classifier.classify(row.description, amount, row.counterparty or None)
            predicted = result.category
            method = result.method.value
            confidence = result.confidence
            needs_review = result.needs_review
        else:
            raise ValueError(f"Unknown evaluation strategy: {strategy}")
        records.append(
            PredictionRecord(
                expected=row.expected_category,
                predicted=predicted,
                language=row.language,
                difficulty=row.difficulty,
                ambiguity=bool(row.ambiguity),
                method=method,
                confidence=confidence,
                needs_review=needs_review,
            )
        )
    return records


def _summarize(records: list[PredictionRecord]) -> MetricSummary:
    if not records:
        raise ValueError("Cannot summarize an empty evaluation slice")
    expected = [record.expected for record in records]
    predicted = [record.predicted or ABSTENTION_LABEL for record in records]
    category_labels = sorted(set(expected))
    accepted = [
        record for record in records if record.predicted is not None and not record.needs_review
    ]

    category_results: list[CategoryResult] = []
    for category in category_labels:
        true_positive = sum(
            record.expected == category and record.predicted == category for record in records
        )
        predicted_positive = sum(record.predicted == category for record in records)
        actual_positive = sum(record.expected == category for record in records)
        precision = true_positive / predicted_positive if predicted_positive else 0.0
        recall = true_positive / actual_positive if actual_positive else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        category_results.append(CategoryResult(category, precision, recall, f1, actual_positive))

    matrix_labels = (*category_labels, ABSTENTION_LABEL)
    matrix = confusion_matrix(expected, predicted, labels=matrix_labels)
    return MetricSummary(
        rows=len(records),
        accuracy=float(accuracy_score(expected, predicted)),
        macro_f1=float(
            f1_score(
                expected,
                predicted,
                labels=category_labels,
                average="macro",
                zero_division=0,
            )
        ),
        prediction_coverage=sum(record.predicted is not None for record in records) / len(records),
        review_rate=sum(record.needs_review for record in records) / len(records),
        auto_acceptance_rate=len(accepted) / len(records),
        selective_accuracy=(
            sum(record.expected == record.predicted for record in accepted) / len(accepted)
            if accepted
            else None
        ),
        rule_coverage=sum(
            record.method == ClassificationMethod.KEYWORD_RULE.value for record in records
        )
        / len(records),
        per_category=tuple(category_results),
        confusion_labels=matrix_labels,
        confusion_matrix=tuple(tuple(int(value) for value in row) for row in matrix),
    )


def evaluate_text_classification_strategies(
    challenge: pd.DataFrame,
    loaded_model: LoadedCategoryModel,
    review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
) -> tuple[StrategyEvaluation, ...]:
    expense_categories = {category.value for category in ExpenseCategory}
    evaluations = []
    for strategy in ("text_rules_only", "tfidf_only", "hybrid"):
        records = _records_for_strategy(challenge, loaded_model, strategy, review_threshold)
        evaluations.append(
            StrategyEvaluation(
                strategy=strategy,
                full_system=_summarize(records),
                expense_only=_summarize(
                    [record for record in records if record.expected in expense_categories]
                ),
                by_language={
                    language: _summarize(
                        [record for record in records if record.language == language]
                    )
                    for language in sorted({record.language for record in records})
                },
                by_difficulty={
                    difficulty: _summarize(
                        [record for record in records if record.difficulty == difficulty]
                    )
                    for difficulty in sorted({record.difficulty for record in records})
                },
                by_ambiguity={
                    str(ambiguity).lower(): _summarize(
                        [record for record in records if record.ambiguity == ambiguity]
                    )
                    for ambiguity in (False, True)
                },
            )
        )
    return tuple(evaluations)


def write_evaluation_report(
    evaluations: tuple[StrategyEvaluation, ...],
    destination: Path = DEFAULT_REPORT_PATH,
    review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
    model_version: str | None = None,
    model_artifact_sha256: str | None = None,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(
            {
                "evaluation_version": EVALUATION_VERSION,
                "challenge_version": CHALLENGE_VERSION,
                "review_threshold": review_threshold,
                "model_version": model_version,
                "model_artifact_sha256": model_artifact_sha256,
                "evaluations": [asdict(evaluation) for evaluation in evaluations],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return destination


def run() -> None:
    challenge = load_text_classification_challenge(DEFAULT_CHALLENGE_PATH)
    loaded_model = load_category_model_artifact()
    evaluations = evaluate_text_classification_strategies(
        challenge,
        loaded_model,
    )
    report_path = write_evaluation_report(
        evaluations,
        model_version=loaded_model.metadata.model_version,
        model_artifact_sha256=calculate_sha256(DEFAULT_ARTIFACT_PATH),
    )
    print(f"Text classification evaluation ready: {report_path}")


if __name__ == "__main__":
    run()
