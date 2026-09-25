import pandas as pd
import pytest
from financial_ai.ml.transaction_classification.data.manual_short_dataset import (
    calculate_manual_short_sha256,
    load_manual_short_dataset,
    validate_manual_short_dataset,
)

EXPECTED_SHA256 = "cfe255a96d49219b90cd94de62d5579d05a593a654eddec0e166bcd71e970887"


def test_manual_short_dataset_has_balanced_locked_splits() -> None:
    data = load_manual_short_dataset()

    assert len(data) == 144
    assert data.groupby("split").size().to_dict() == {
        "test": 48,
        "train": 48,
        "validation": 48,
    }
    assert data.groupby(["split", "language", "category"]).size().eq(2).all()
    assert calculate_manual_short_sha256() == EXPECTED_SHA256


def test_manual_short_checksum_is_independent_of_checkout_line_endings(tmp_path) -> None:
    source = tmp_path / "manual_short.csv"
    source.write_bytes(b"text,category\nMiete,housing\n")
    expected = calculate_manual_short_sha256(source)
    source.write_bytes(b"text,category\r\nMiete,housing\r\n")
    assert calculate_manual_short_sha256(source) == expected


def test_manual_short_dataset_rejects_phrase_and_novel_concept_leakage() -> None:
    data = load_manual_short_dataset()
    phrase_leakage = data.copy()
    validation_index = phrase_leakage.index[phrase_leakage["split"].eq("validation")][0]
    phrase_leakage.loc[validation_index, "phrase_family"] = data.loc[0, "phrase_family"]
    phrase_leakage.loc[validation_index, "language"] = data.loc[0, "language"]
    with pytest.raises(ValueError, match="phrase families"):
        validate_manual_short_dataset(phrase_leakage)

    novel_leakage = pd.concat(
        [
            data,
            data.loc[data["generalization_slice"].eq("novel_concept")]
            .iloc[[0]]
            .assign(
                id="duplicate-concept",
                phrase_family="novel-duplicate-test",
                split="test",
            ),
        ],
        ignore_index=True,
    )
    with pytest.raises(ValueError, match="Novel concepts"):
        validate_manual_short_dataset(novel_leakage)
