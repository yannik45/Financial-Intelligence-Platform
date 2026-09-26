from financial_ai.ml.transaction_classification.data.english_training_generator_v1 import (
    write_english_training_dataset_v1,
)
from financial_ai.ml.transaction_classification.data.german_training_generator_v2 import (
    write_german_training_dataset_v2,
)
from financial_ai.ml.transaction_classification.modeling.category_artifact import (
    DEFAULT_ARTIFACT_PATH,
    ModelArtifactError,
    build_category_model_artifact,
    load_category_model_artifact,
)
from financial_ai.ml.transaction_classification.modeling.semantic_artifact import (
    DEFAULT_ARTIFACT_PATH as DEFAULT_SEMANTIC_ARTIFACT_PATH,
)
from financial_ai.ml.transaction_classification.modeling.semantic_artifact import (
    DEFAULT_METADATA_PATH as DEFAULT_SEMANTIC_METADATA_PATH,
)
from financial_ai.ml.transaction_classification.modeling.semantic_artifact import (
    SemanticArtifactError,
    build_semantic_head_artifact,
    load_semantic_head_artifact,
)
from financial_ai.ml.transaction_classification.modeling.semantic_embeddings import (
    load_sentence_encoder,
)


def bootstrap_category_model() -> None:
    english_path, _ = write_english_training_dataset_v1()
    german_path, _ = write_german_training_dataset_v2()
    try:
        metadata = load_category_model_artifact().metadata
    except ModelArtifactError:
        metadata = build_category_model_artifact(
            english_path=english_path,
            german_path=german_path,
        )
    print(f"Category model ready: {DEFAULT_ARTIFACT_PATH} ({metadata.training_rows} training rows)")
    try:
        semantic_metadata = load_semantic_head_artifact().metadata
    except SemanticArtifactError:
        try:
            encoder = load_sentence_encoder()
            semantic_metadata = build_semantic_head_artifact(encoder)
        except (RuntimeError, OSError) as exc:
            print(f"Semantic category head unavailable; TF-IDF fallback remains active: {exc}")
            return
    print(
        f"Semantic category head ready: {DEFAULT_SEMANTIC_ARTIFACT_PATH} "
        f"({semantic_metadata.training_rows} training rows; "
        f"metadata {DEFAULT_SEMANTIC_METADATA_PATH})"
    )


def run() -> None:
    bootstrap_category_model()


if __name__ == "__main__":
    run()
