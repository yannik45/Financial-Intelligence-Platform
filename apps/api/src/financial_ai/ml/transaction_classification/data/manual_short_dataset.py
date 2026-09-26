from pathlib import Path

import pandas as pd

from financial_ai.ml.artifact_integrity import calculate_canonical_text_sha256

DEFAULT_MANUAL_SHORT_PATH = Path("data/development/transaction_categories/manual_short_v2.csv")
EXPECTED_SPLITS = {"train", "validation", "test"}
EXPECTED_SLICES = {"training", "known_concept_new_phrase", "novel_concept"}
REQUIRED_COLUMNS = {
    "id",
    "text",
    "category",
    "language",
    "concept_group",
    "phrase_family",
    "split",
    "generalization_slice",
}


def calculate_manual_short_sha256(path: Path = DEFAULT_MANUAL_SHORT_PATH) -> str:
    return calculate_canonical_text_sha256(path)


def validate_manual_short_dataset(data: pd.DataFrame) -> None:
    missing = REQUIRED_COLUMNS.difference(data.columns)
    if missing:
        raise ValueError(f"Missing manual-short columns: {sorted(missing)}")
    if set(data["split"]) != EXPECTED_SPLITS:
        raise ValueError(f"Expected splits {sorted(EXPECTED_SPLITS)}")
    if not set(data["generalization_slice"]).issubset(EXPECTED_SLICES):
        raise ValueError("Unsupported manual-short generalization slice")
    if data["id"].duplicated().any():
        raise ValueError("Manual-short IDs must be unique")
    if data["text"].str.strip().eq("").any():
        raise ValueError("Manual-short text must not be empty")

    phrase_split_counts = data.groupby(["language", "phrase_family"])["split"].nunique()
    if (phrase_split_counts > 1).any():
        raise ValueError("Manual-short phrase families must not cross splits")

    novel_rows = data.loc[data["generalization_slice"].eq("novel_concept")]
    novel_split_counts = novel_rows.groupby(["language", "category", "concept_group"])[
        "split"
    ].nunique()
    if (novel_split_counts > 1).any():
        raise ValueError("Novel concepts must not cross evaluation splits")

    train_concepts = set(
        data.loc[data["split"].eq("train"), ["language", "category", "concept_group"]].itertuples(
            index=False, name=None
        )
    )
    evaluation_rows = data.loc[~data["split"].eq("train")]
    for row in evaluation_rows.itertuples(index=False):
        concept_key = (row.language, row.category, row.concept_group)
        if (
            row.generalization_slice == "known_concept_new_phrase"
            and concept_key not in train_concepts
        ):
            raise ValueError("Known-concept rows must reference a training concept")
        if row.generalization_slice == "novel_concept" and concept_key in train_concepts:
            raise ValueError("Novel-concept rows must not reference a training concept")


def load_manual_short_dataset(
    path: Path = DEFAULT_MANUAL_SHORT_PATH,
) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Manual-short dataset not found: {path}")
    data = pd.read_csv(path, dtype=str, keep_default_na=False)
    validate_manual_short_dataset(data)
    return data
