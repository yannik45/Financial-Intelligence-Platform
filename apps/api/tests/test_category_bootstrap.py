from financial_ai.ml.transaction_classification.modeling import category_bootstrap
from financial_ai.ml.transaction_classification.modeling.category_artifact import (
    ModelArtifactError,
)


def test_bootstrap_generates_training_sources_before_model(monkeypatch, tmp_path):
    english_path = tmp_path / "english.csv"
    german_path = tmp_path / "german.csv"
    calls: list[str] = []

    monkeypatch.setattr(
        category_bootstrap,
        "write_english_training_dataset_v1",
        lambda: (calls.append("english") or english_path, tmp_path / "english.json"),
    )
    monkeypatch.setattr(
        category_bootstrap,
        "write_german_training_dataset_v2",
        lambda: (calls.append("german") or german_path, tmp_path / "german.json"),
    )

    class Metadata:
        training_rows = 21_000

    def build_model(*, english_path, german_path):
        assert english_path == tmp_path / "english.csv"
        assert german_path == tmp_path / "german.csv"
        calls.append("model")
        return Metadata()

    monkeypatch.setattr(category_bootstrap, "build_category_model_artifact", build_model)
    monkeypatch.setattr(
        category_bootstrap,
        "load_category_model_artifact",
        lambda: (_ for _ in ()).throw(ModelArtifactError("missing")),
    )

    class SemanticMetadata:
        training_rows = 16_500

    class LoadedSemanticHead:
        metadata = SemanticMetadata()

    monkeypatch.setattr(
        category_bootstrap,
        "load_semantic_head_artifact",
        lambda: LoadedSemanticHead(),
    )

    category_bootstrap.bootstrap_category_model()

    assert calls == ["english", "german", "model"]
