import copy

import pytest

from axral_vocal_ai.pitch_training_contract_splits import (
    PitchTrainingSplitError,
    assign_example_splits,
)


def make_record(example_id, *, source_id=None, split_group=None, project_id=None, session_id=None):
    provenance = {
        "source_kind": "human_labeled_project",
        "source_id": source_id or f"source-{example_id}",
        "license_or_permission": "permission-ref",
        "consent_status": "verified",
        "created_at": "2026-01-01",
    }
    if project_id is not None:
        provenance["project_id"] = project_id
    if session_id is not None:
        provenance["session_id"] = session_id
    return {
        "record_schema": "axral.pitch-training-example",
        "schema_version": "1.0",
        "example_id": example_id,
        "provenance": provenance,
        "voicebank": {
            "profile_id": f"bank-{example_id}",
            "profile_version": "1",
            "phoneme_scheme": "utau-alias",
            "split_group": split_group or f"group-{example_id}",
        },
        "context": {
            "midi_note": 60,
            "start_ms": 0.0,
            "duration_ms": 500.0,
            "lyric": "あ",
            "resolved_alias": "あ",
            "voiced": True,
            "baseline_pitch": [
                {"time_ms": 0.0, "hz": 261.6256},
                {"time_ms": 500.0, "hz": 261.6256},
            ],
        },
        "target": {
            "kind": "pitch_delta",
            "points": [
                {"time_ms": 0.0, "delta_cents": 0.0},
                {"time_ms": 500.0, "delta_cents": 0.0},
            ],
            "label_source": "human_reviewed",
            "review_status": "approved",
        },
    }


def test_assigns_all_splits_deterministically_without_mutating_input():
    records = [make_record(f"ex-{index}") for index in range(6)]
    original = copy.deepcopy(records)

    assigned = assign_example_splits(records)
    reversed_assigned = assign_example_splits(list(reversed(records)))

    assert records == original
    assert {record["split"] for record in assigned} == {"train", "validation", "test"}
    assert {
        record["example_id"]: record["split"] for record in assigned
    } == {
        record["example_id"]: record["split"] for record in reversed_assigned
    }


def test_shared_voicebank_split_group_never_crosses_splits():
    records = [
        make_record("a", split_group="bank-family"),
        make_record("b", split_group="bank-family"),
        make_record("c"),
        make_record("d"),
    ]

    assigned = assign_example_splits(records)
    by_id = {record["example_id"]: record for record in assigned}

    assert by_id["a"]["split"] == by_id["b"]["split"]


def test_source_and_project_session_groups_connect_transitively():
    records = [
        make_record("a", source_id="shared-source"),
        make_record("b", source_id="shared-source", project_id="project-x"),
        make_record("c", project_id="project-x", session_id="session-x"),
        make_record("d"),
        make_record("e"),
    ]

    assigned = assign_example_splits(records)
    by_id = {record["example_id"]: record["split"] for record in assigned}

    assert by_id["a"] == by_id["b"] == by_id["c"]


def test_custom_ratios_are_supported():
    records = [make_record(f"ex-{index}") for index in range(5)]

    assigned = assign_example_splits(
        records, ratios={"train": 0.6, "validation": 0.2, "test": 0.2}
    )

    assert {record["split"] for record in assigned} == {"train", "validation", "test"}


@pytest.mark.parametrize(
    "ratios",
    [
        {"train": 1, "validation": 1},
        {"train": 0, "validation": 1, "test": 1},
        {"train": float("nan"), "validation": 1, "test": 1},
        {"train": True, "validation": 1, "test": 1},
        {"train": 1e308, "validation": 1e308, "test": 1e308},
    ],
)
def test_rejects_invalid_ratios(ratios):
    with pytest.raises(PitchTrainingSplitError):
        assign_example_splits([make_record("one")], ratios=ratios)


def test_rejects_duplicate_example_ids_and_empty_input():
    with pytest.raises(PitchTrainingSplitError, match="duplicate example_id"):
        assign_example_splits([make_record("same"), make_record("same")])
    with pytest.raises(PitchTrainingSplitError, match="no example records"):
        assign_example_splits([])


def test_rejects_invalid_contract_records():
    invalid = make_record("bad")
    invalid["provenance"]["consent_status"] = "unknown"

    with pytest.raises(PitchTrainingSplitError, match="permission_not_verified"):
        assign_example_splits([invalid])


def test_overwrites_existing_split_values():
    record = make_record("one")
    record["split"] = "test"

    assigned = assign_example_splits([record])

    assert assigned[0]["split"] in {"train", "validation", "test"}
    assert record["split"] == "test"
