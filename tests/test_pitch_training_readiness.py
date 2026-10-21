import copy

from axral_vocal_ai.pitch_training_contract_splits import assign_example_splits
from axral_vocal_ai.pitch_training_readiness import assess_training_candidate
from test_pitch_training_contract_splits import make_record


def test_synthetic_fixture_never_passes_training_candidate_gate():
    records = assign_example_splits([make_record(f"ex-{index}") for index in range(6)])
    result = assess_training_candidate(
        records, schema="axral.pitch-training-example-1.0", dataset_origin="synthetic_fixture"
    )

    assert result["status"] == "blocked"
    assert "dataset_origin_not_candidate_real_data" in result["reasons"]
    assert result["training_started"] is False


def test_candidate_real_data_can_only_reach_human_review_gate():
    records = assign_example_splits([make_record(f"ex-{index}") for index in range(6)])
    original = copy.deepcopy(records)

    result = assess_training_candidate(
        records, schema="axral.pitch-training-example-1.0", dataset_origin="candidate_real_data"
    )

    assert records == original
    assert result["status"] == "candidate_for_human_training_review"
    assert result["reasons"] == []
    assert result["training_started"] is False
    assert "does not authorize training" in result["authorization_warning"]


def test_candidate_gate_blocks_missing_approved_labels():
    records = assign_example_splits([make_record(f"ex-{index}") for index in range(6)])
    records[0]["target"]["review_status"] = "review_required"

    result = assess_training_candidate(
        records, schema="axral.pitch-training-example-1.0", dataset_origin="candidate_real_data"
    )

    assert result["status"] == "blocked"
    assert "invalid_records_or_split_leakage" in result["reasons"]
    assert "manual_review_not_approved" in result["reasons"]


def test_rejects_unknown_schema():
    try:
        assess_training_candidate([], schema="unknown")
    except ValueError as exc:
        assert "schema must be" in str(exc)
    else:
        raise AssertionError("unknown schema must be rejected")


from test_training_data import make_record as make_legacy_record, make_target as make_legacy_target


def _legacy_candidate_records():
    rows = [
        make_legacy_record("legacy-train", "bank-a", "train", target=make_legacy_target()),
        make_legacy_record("legacy-validation", "bank-b", "validation", target=make_legacy_target()),
        make_legacy_record("legacy-test", "bank-c", "test", target=make_legacy_target()),
    ]
    for row in rows:
        row["provenance"]["acquisition_method"] = "human-labeled-project"
        row["provenance"]["source_reference"] = "permission-record-" + row["record_id"]
    return rows


def test_legacy_candidate_schema_can_reach_human_review_gate():
    records = _legacy_candidate_records()

    result = assess_training_candidate(
        records, schema="legacy-manifest-v1", dataset_origin="candidate_real_data"
    )

    assert result["status"] == "candidate_for_human_training_review"
    assert result["reasons"] == []
    assert result["records_by_split"] == {"train": 1, "validation": 1, "test": 1}
    assert result["training_started"] is False


def test_legacy_candidate_gate_blocks_unlabeled_record():
    records = _legacy_candidate_records()
    records[1]["target"] = None

    result = assess_training_candidate(
        records, schema="legacy-manifest-v1", dataset_origin="candidate_real_data"
    )

    assert result["status"] == "blocked"
    assert "invalid_records_or_split_leakage" in result["reasons"]
    assert "missing_or_unreviewed_pitch_labels" in result["reasons"]
