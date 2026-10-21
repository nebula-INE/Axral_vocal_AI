import copy

from axral_vocal_ai.pitch_training_pipeline import (
    prepare_example_dataset,
    prepare_legacy_dataset,
)
from test_pitch_training_splits import make_record as make_legacy_record
from test_pitch_training_contract_splits import make_record as make_example_record


def test_legacy_pipeline_assigns_splits_and_reports_without_mutating_input():
    records = [
        make_legacy_record(f"record-{index}", f"bank-{index}", f"source-{index}", f"project-{index}/session-{index}")
        for index in range(6)
    ]
    original = copy.deepcopy(records)

    result = prepare_legacy_dataset(records)

    assert records == original
    assert result["schema"] == "legacy-manifest-v1"
    assert result["status"] == "ready_for_manual_review"
    assert result["training_started"] is False
    assert result["quality_report"]["records_valid"] == 6
    assert set(row["split"] for row in result["records"]) == {"train", "validation", "test"}


def test_example_pipeline_assigns_splits_and_reports_without_mutating_input():
    records = [make_example_record(f"example-{index}") for index in range(6)]
    original = copy.deepcopy(records)

    result = prepare_example_dataset(records)

    assert records == original
    assert result["schema"] == "axral.pitch-training-example-1.0"
    assert result["status"] == "ready_for_manual_review"
    assert result["training_started"] is False
    assert result["quality_report"]["records_valid"] == 6
    assert set(row["split"] for row in result["records"]) == {"train", "validation", "test"}


def test_pipeline_rejects_invalid_example_records_before_preparation():
    invalid = make_example_record("invalid-example")
    invalid["provenance"]["consent_status"] = "unknown"

    try:
        prepare_example_dataset([invalid])
    except ValueError as exc:
        assert "record 1 is invalid" in str(exc)
    else:
        raise AssertionError("invalid records must not enter preparation")
