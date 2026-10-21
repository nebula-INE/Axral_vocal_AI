import json

import pytest

from axral_vocal_ai.pitch_training_contract import validate_jsonl_text, validate_record


def make_record(example_id="example-1"):
    return {
        "record_schema": "axral.pitch-training-example",
        "schema_version": "1.0",
        "example_id": example_id,
        "provenance": {
            "source_kind": "human_labeled_project",
            "source_id": "opaque-source-1",
            "license_or_permission": "permission-ref-1",
            "consent_status": "verified",
            "created_at": "2026-01-01",
        },
        "voicebank": {
            "profile_id": "bank-a",
            "profile_version": "1",
            "phoneme_scheme": "utau-alias",
            "split_group": "bank-a",
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
                {"time_ms": 250.0, "hz": 261.6256},
                {"time_ms": 500.0, "hz": 261.6256},
            ],
        },
        "target": {
            "kind": "pitch_delta",
            "points": [
                {"time_ms": 0.0, "delta_cents": 0.0},
                {"time_ms": 250.0, "delta_cents": 18.0},
                {"time_ms": 500.0, "delta_cents": 0.0},
            ],
            "label_source": "human_reviewed",
            "review_status": "approved",
        },
    }


def test_accepts_contract_example_and_reports_counts():
    report = validate_jsonl_text(json.dumps(make_record(), ensure_ascii=False) + "\n")

    assert report.accepted_count == 1
    assert report.rejected_count == 0
    assert report.accepted[0]["example_id"] == "example-1"


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (lambda r: r.update(record_schema="wrong.schema"), "unsupported_schema"),
        (lambda r: r.update(schema_version="2.0"), "unsupported_version"),
        (lambda r: r["provenance"].update(consent_status="unknown"), "permission_not_verified"),
        (lambda r: r["provenance"].update(license_or_permission=""), "missing_provenance"),
        (lambda r: r["target"].update(review_status="draft"), "label_not_approved"),
        (lambda r: r["target"].update(label_source="deterministic-no-op-stub"), "stub_is_not_label"),
        (lambda r: r["context"].update(midi_note=True), "invalid_midi_note"),
        (lambda r: r["context"].update(duration_ms=-1), "negative_duration"),
        (lambda r: r["context"]["baseline_pitch"][1].update(hz=0), "invalid_baseline_hz"),
        (lambda r: r["target"]["points"][1].update(delta_cents=float("nan")), "invalid_delta"),
        (lambda r: r["target"]["points"][1].update(time_ms=600), "target_out_of_range"),
        (lambda r: r["target"]["points"].reverse(), "unordered_target"),
    ],
)
def test_rejects_invalid_records(mutate, expected_code):
    record = make_record()
    mutate(record)

    issues = validate_record(record)

    assert expected_code in {code for code, _ in issues}


def test_rejects_malformed_json_and_non_object_records():
    report = validate_jsonl_text('{"example_id":\n[]\n')

    assert report.accepted_count == 0
    assert {item.code for item in report.rejected} == {"invalid_json", "record_not_object"}


def test_duplicate_ids_reject_every_occurrence():
    first = make_record("same")
    second = make_record("same")
    report = validate_jsonl_text("\n".join(json.dumps(r, ensure_ascii=False) for r in (first, second)))

    assert report.accepted_count == 0
    assert [item.code for item in report.rejected] == ["duplicate_example_id", "duplicate_example_id"]


def test_unvoiced_note_cannot_have_pitch_delta_points():
    record = make_record()
    record["context"]["voiced"] = False
    record["context"]["baseline_pitch"] = []
    issues = validate_record(record)

    assert "unvoiced_target" in {code for code, _ in issues}
    assert "empty_baseline" not in {code for code, _ in issues}


def test_unvoiced_note_with_empty_target_points_is_valid():
    record = make_record()
    record["context"]["voiced"] = False
    record["context"]["baseline_pitch"] = []
    record["target"]["points"] = []

    assert validate_record(record) == ()


def test_rejection_counts_are_machine_readable():
    report = validate_jsonl_text("\n".join([
        json.dumps(make_record("duplicate")),
        json.dumps(make_record("duplicate")),
        "not json",
    ]))

    assert report.rejection_counts == {"duplicate_example_id": 2, "invalid_json": 1}
