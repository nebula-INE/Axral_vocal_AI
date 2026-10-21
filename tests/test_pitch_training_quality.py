import copy

from axral_vocal_ai.pitch_training_quality import report_example_records, report_legacy_records
from test_training_data import make_record as make_legacy_record, make_target as make_legacy_target
from test_pitch_training_contract import make_record as make_example_record


def test_legacy_report_aggregates_without_exposing_identifiers():
    rows = [
        make_legacy_record("private-record-1", "bank-private-a", "train", target=make_legacy_target()),
        make_legacy_record("private-record-2", "bank-private-b", "validation"),
        make_legacy_record("private-record-3", "bank-private-c", "test", permission="review_required"),
    ]
    report = report_legacy_records(rows)

    assert report["schema"] == "legacy-manifest-v1"
    assert report["records_total"] == 3
    assert report["records_valid"] == 2
    assert report["records_invalid"] == 1
    assert report["records_by_split"] == {"train": 1, "validation": 1, "test": 0}
    assert report["label_status_counts"] == {"labeled": 1, "unlabeled": 2}
    assert report["dataset_origin"] == "synthetic_fixture"
    assert report["synthetic_or_fixture_records"] == 3
    serialized = str(report)
    assert "private-record" not in serialized
    assert "bank-private" not in serialized


def test_example_report_counts_rejection_codes_and_consent():
    good = make_example_record("private-example-1")
    bad = make_example_record("private-example-2")
    bad["provenance"]["consent_status"] = "unknown"
    report = report_example_records([good, bad])

    assert report["records_total"] == 2
    assert report["records_valid"] == 1
    assert report["records_invalid"] == 1
    assert report["validation_issue_counts"] == {"permission_not_verified": 1}
    assert report["consent_status_counts"] == {"unknown": 1, "verified": 1}
    assert report["voicebank_group_count"] == 1
    assert "private-example" not in str(report)


def test_example_report_does_not_mutate_input_and_marks_fixture_origin():
    row = make_example_record()
    original = copy.deepcopy(row)

    report = report_example_records([row])

    assert row == original
    assert report["dataset_origin"] == "synthetic_fixture"
    assert "not evidence of real-data quality" in report["origin_warning"]
    assert report["non_synthetic_declared_records"] == 1
    assert report["synthetic_or_fixture_records"] == 0


def test_real_candidate_origin_is_not_claimed_as_verified():
    report = report_example_records([make_example_record()], dataset_origin="candidate_real_data")

    assert report["dataset_origin"] == "candidate_real_data"
    assert "do not independently verify rights" in report["origin_warning"]


def test_invalid_origin_is_rejected():
    try:
        report_legacy_records([], dataset_origin="verified_real_data")
    except ValueError as exc:
        assert "dataset_origin" in str(exc)
    else:
        raise AssertionError("invalid dataset_origin should fail")



def test_duplicate_example_ids_are_counted_invalid():
    report = report_example_records([
        make_example_record("same-private-id"),
        make_example_record("same-private-id"),
    ])

    assert report["records_valid"] == 0
    assert report["records_invalid"] == 2
    assert report["validation_issue_counts"] == {"duplicate_example_id": 2}


def test_legacy_split_leakage_marks_both_records_invalid():
    first = make_legacy_record("train-private", "same-bank", "train")
    second = make_legacy_record("test-private", "same-bank", "test")

    report = report_legacy_records([first, second])

    assert report["records_valid"] == 0
    assert report["records_invalid"] == 2
    assert report["validation_issue_counts"] == {"voicebank_split_leakage": 1}
