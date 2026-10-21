import copy

import pytest

from axral_vocal_ai.pitch_training_evaluation import (
    PitchEvaluationManifestError,
    validate_evaluation_manifest,
)


def _manifest():
    digest = "a" * 64
    return {
        "evaluation_id": "eval-001",
        "schema": "axral.pitch-training-example-1.0",
        "dataset_snapshot_sha256": digest,
        "test_dataset_snapshot_sha256": "d" * 64,
        "model_artifact_sha256": "b" * 64,
        "code_revision": "c" * 64,
        "seed": 17,
        "evaluated_split": "test",
        "evaluated_records": 120,
        "metrics": {"mae_cents": 12.5, "within_20_cents": 0.82},
        "test_split_used_for_tuning": False,
    }


def test_valid_manifest_returns_reproducibility_summary_without_starting_training():
    manifest = _manifest()
    original = copy.deepcopy(manifest)

    result = validate_evaluation_manifest(manifest)

    assert manifest == original
    assert result["status"] == "ready_for_human_review"
    assert result["evaluated_split"] == "test"
    assert result["metric_names"] == ["mae_cents", "within_20_cents"]
    assert result["reproducibility"]["seed"] == 17
    assert result["reproducibility"]["test_dataset_snapshot_sha256"] == "d" * 64
    assert result["training_started"] is False
    assert "does not verify" in result["warning"]


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("evaluated_split", "validation", "evaluation_must_use_test_split"),
        ("test_split_used_for_tuning", True, "test_split_must_not_be_used_for_tuning"),
        ("evaluated_records", 0, "evaluated_records_must_be_positive"),
        ("seed", True, "invalid_seed"),
        ("dataset_snapshot_sha256", "not-a-digest", "invalid_dataset_snapshot_sha256"),
        ("test_dataset_snapshot_sha256", "not-a-digest", "invalid_test_dataset_snapshot_sha256"),
        ("metrics", {"mae_cents": float("nan")}, "invalid_metric_value:mae_cents"),
    ],
)
def test_rejects_invalid_or_test_contaminated_manifest(field, value, reason):
    manifest = _manifest()
    manifest[field] = value

    with pytest.raises(PitchEvaluationManifestError, match=reason):
        validate_evaluation_manifest(manifest)


def test_rejects_non_string_schema_without_type_error():
    manifest = _manifest()
    manifest["schema"] = []

    with pytest.raises(PitchEvaluationManifestError, match="unsupported_schema"):
        validate_evaluation_manifest(manifest)


def test_rejects_missing_reproducibility_fields():
    manifest = _manifest()
    del manifest["code_revision"]

    with pytest.raises(PitchEvaluationManifestError, match="missing_code_revision"):
        validate_evaluation_manifest(manifest)


def test_rejects_missing_held_out_test_snapshot_digest():
    manifest = _manifest()
    del manifest["test_dataset_snapshot_sha256"]

    with pytest.raises(PitchEvaluationManifestError, match="missing_test_dataset_snapshot_sha256"):
        validate_evaluation_manifest(manifest)
