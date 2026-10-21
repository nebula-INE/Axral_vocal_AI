import copy

import pytest

from axral_vocal_ai.pitch_training_splits import assign_splits
from axral_vocal_ai.training_data import DatasetValidationError, validate_records


def make_record(record_id, bank, source, source_reference):
    return {
        "schema_version": 1,
        "record_id": record_id,
        "source_id": source,
        "permission_status": "approved",
        "license_id": "INTERNAL-ML-PERMISSION-001",
        "voicebank_id": bank,
        "split": "train",
        "input": {
            "notes": [
                {"start_sec": 0.0, "end_sec": 0.4, "midi_note": 60, "lyric": "あ", "voiced": True}
            ]
        },
        "target": None,
        "provenance": {
            "acquisition_method": "curated fixture",
            "source_reference": source_reference,
            "review_date": "2026-10-11",
            "review_status": "approved",
        },
        "preprocessing": {"tool_version": "fixture-1", "transformations": []},
    }


def split_by_id(records):
    return {record["record_id"]: record["split"] for record in records}


def test_assign_splits_is_deterministic_and_does_not_mutate_inputs():
    records = [
        make_record("r1", "bank-a", "source-a", "project-a/session-a"),
        make_record("r2", "bank-b", "source-b", "project-b/session-b"),
        make_record("r3", "bank-c", "source-c", "project-c/session-c"),
        make_record("r4", "bank-d", "source-d", "project-d/session-d"),
        make_record("r5", "bank-e", "source-e", "project-e/session-e"),
        make_record("r6", "bank-f", "source-f", "project-f/session-f"),
    ]
    original = copy.deepcopy(records)

    first = assign_splits(records)
    second = assign_splits(list(reversed(records)))

    assert split_by_id(first) == split_by_id(second)
    assert records == original
    assert {row["split"] for row in first} == {"train", "validation", "test"}
    assert validate_records(first)["status"] == "valid"


def test_assign_splits_keeps_voicebank_and_source_groups_together_transitively():
    records = [
        make_record("r1", "bank-a", "source-a", "project-a/session-a"),
        # Shares bank with r1 and source reference with r3, joining all three.
        make_record("r2", "bank-a", "source-b", "project-b/session-b"),
        make_record("r3", "bank-c", "source-c", "project-b/session-b"),
        make_record("r4", "bank-d", "source-d", "project-d/session-d"),
        make_record("r5", "bank-e", "source-e", "project-e/session-e"),
    ]

    result = assign_splits(records)
    by_id = split_by_id(result)

    assert by_id["r1"] == by_id["r2"] == by_id["r3"]
    assert by_id["r4"] != by_id["r1"] or by_id["r5"] != by_id["r1"]
    validate_records(result)


def test_assign_splits_uses_configured_ratios_and_replaces_old_split_values():
    records = [
        make_record("r1", "bank-a", "source-a", "session-a"),
        make_record("r2", "bank-b", "source-b", "session-b"),
        make_record("r3", "bank-c", "source-c", "session-c"),
    ]
    for row in records:
        row["split"] = "test"

    result = assign_splits(records, {"train": 1, "validation": 1, "test": 1})

    assert {row["split"] for row in result} == {"train", "validation", "test"}


@pytest.mark.parametrize(
    "ratios",
    [
        {"train": 1, "validation": 0, "test": 1},
        {"train": 1, "validation": -1, "test": 1},
        {"train": float("nan"), "validation": 1, "test": 1},
        {"train": True, "validation": 1, "test": 1},
        {"train": 1, "validation": 1},
    ],
)
def test_assign_splits_rejects_invalid_ratios(ratios):
    records = [make_record("r1", "bank-a", "source-a", "session-a")]
    with pytest.raises(DatasetValidationError, match="ratio"):
        assign_splits(records, ratios)


def test_assign_splits_rejects_duplicate_record_ids():
    records = [
        make_record("same", "bank-a", "source-a", "session-a"),
        make_record("same", "bank-b", "source-b", "session-b"),
    ]
    with pytest.raises(DatasetValidationError, match="duplicate record_id"):
        assign_splits(records)


def test_assign_splits_rejects_empty_input():
    with pytest.raises(DatasetValidationError, match="no records"):
        assign_splits([])
