import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score

from financial_ai.ml.artifact_integrity import calculate_canonical_text_sha256
from financial_ai.ml.transaction_classification.data.classification_v2_dataset import (
    ClassificationV2Dataset,
    load_classification_v2_dataset,
)
from financial_ai.ml.transaction_classification.data.manual_short_dataset import (
    calculate_manual_short_sha256,
)
from financial_ai.ml.transaction_classification.modeling.semantic_embeddings import (
    ENCODER_ID,
    ENCODER_REVISION,
    SentenceEncoder,
    load_or_create_embedding_cache,
    load_sentence_encoder,
)

SELECTION_PATH = Path(
    "data/evaluation/transaction_categories/classification_v2_model_selection.json"
)
DEFAULT_RESULT_PATH = Path(
    "data/evaluation/transaction_categories/classification_v2_manual_test.json"
)
RANDOM_STATE = 42


@dataclass(frozen=True)
class ManualTestReport:
    candidate: str
    encoder_id: str
    encoder_revision: str
    dataset_sha256: str
    selection_sha256: str
    training_rows: int
    test_rows: int
    in_scope_rows: int
    accuracy: float
    macro_f1: float
    threshold: float
    automatic_coverage: float
    automatically_accepted_accuracy: float | None
    other_rows: int
    other_rejection_rate: float
    other_false_automatic_acceptance_rate: float
    generalization_accuracy: dict[str, float]
    test_partition_used: bool


def _sha256(path: Path) -> str:
    return calculate_canonical_text_sha256(path)


def evaluate_manual_test_predictions(
    test: pd.DataFrame,
    predictions: np.ndarray,
    confidence: np.ndarray,
    *,
    threshold: float,
    training_rows: int,
) -> ManualTestReport:
    in_scope = test["target_category"].ne("other").to_numpy()
    other = ~in_scope
    accepted = confidence[in_scope] >= threshold
    correctness = predictions[in_scope] == test.loc[in_scope, "target_category"].to_numpy()
    other_accepted = confidence[other] >= threshold
    return ManualTestReport(
        candidate="frozen-multilingual-e5-small-logistic-v1",
        encoder_id=ENCODER_ID,
        encoder_revision=ENCODER_REVISION,
        dataset_sha256=calculate_manual_short_sha256(),
        selection_sha256=_sha256(SELECTION_PATH),
        training_rows=training_rows,
        test_rows=len(test),
        in_scope_rows=int(in_scope.sum()),
        accuracy=float(
            accuracy_score(test.loc[in_scope, "target_category"], predictions[in_scope])
        ),
        macro_f1=float(
            f1_score(
                test.loc[in_scope, "target_category"],
                predictions[in_scope],
                average="macro",
                zero_division=0,
            )
        ),
        threshold=threshold,
        automatic_coverage=float(accepted.mean()),
        automatically_accepted_accuracy=(
            float(correctness[accepted].mean()) if accepted.any() else None
        ),
        other_rows=int(other.sum()),
        other_rejection_rate=float((~other_accepted).mean()),
        other_false_automatic_acceptance_rate=float(other_accepted.mean()),
        generalization_accuracy={
            name: float((predictions[mask] == test.loc[mask, "target_category"].to_numpy()).mean())
            for name in ("known_concept_new_phrase", "novel_concept")
            if (mask := (test["generalization_slice"].eq(name).to_numpy() & in_scope)).any()
        },
        test_partition_used=True,
    )


def run_final_manual_test(
    dataset: ClassificationV2Dataset,
    encoder: SentenceEncoder,
) -> ManualTestReport:
    selection = json.loads(SELECTION_PATH.read_text(encoding="utf-8"))
    manual_selection = selection["routing"]["manual_short"]
    if selection["test_partition_used"]:
        raise ValueError("Model selection must be fixed before final test evaluation")
    if manual_selection["candidate"] != "frozen-multilingual-e5-small-logistic-v1":
        raise ValueError("Unexpected manual-short candidate in model selection")

    training = dataset.train.loc[
        dataset.train["input_slice"].eq("bank_feed") & dataset.train["target_category"].ne("other")
    ].reset_index(drop=True)
    validation = dataset.validation.reset_index(drop=True)
    development_embedding_rows = pd.concat(
        [
            training[["example_id", "description"]],
            validation[["example_id", "description"]],
        ],
        ignore_index=True,
    )
    development_embeddings = load_or_create_embedding_cache(
        development_embedding_rows, encoder
    ).values[: len(training)]

    manual_test = dataset.test.loc[dataset.test["input_slice"].eq("manual_short")].reset_index(
        drop=True
    )
    test_embeddings = load_or_create_embedding_cache(
        manual_test[["example_id", "description"]], encoder
    ).values
    classifier = LogisticRegression(
        C=1.0,
        class_weight="balanced",
        max_iter=1_000,
        random_state=RANDOM_STATE,
    )
    classifier.fit(development_embeddings, training["target_category"])
    predictions = classifier.predict(test_embeddings)
    confidence = classifier.predict_proba(test_embeddings).max(axis=1)
    return evaluate_manual_test_predictions(
        manual_test,
        predictions,
        confidence,
        threshold=float(manual_selection["threshold"]),
        training_rows=len(training),
    )


def run() -> None:
    dataset = load_classification_v2_dataset()
    encoder = load_sentence_encoder()
    report = run_final_manual_test(dataset, encoder)
    serialized = json.dumps(asdict(report), indent=2) + "\n"
    if DEFAULT_RESULT_PATH.is_file():
        if DEFAULT_RESULT_PATH.read_text(encoding="utf-8") != serialized:
            raise ValueError("Existing final test result differs from reproduction")
    else:
        DEFAULT_RESULT_PATH.write_text(serialized, encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    run()
