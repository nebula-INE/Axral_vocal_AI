import json

from axral_vocal_ai.dataset_audit import audit_dataset
from axral_vocal_ai.training_data import validate_jsonl


def record(record_id, bank, split, notes, points):
    return {
        "schema_version": 1,
        "record_id": record_id,
        "source_id": record_id,
        "permission_status": "approved",
        "license_id": "INTERNAL-ML-PERMISSION-001",
        "voicebank_id": bank,
        "split": split,
        "input": {"notes": notes},
        "target": {
            "kind": "pitch_delta_semitones",
            "points": points,
            "label_source": "synthetic_fixture",
            "confidence": 1.0,
        },
        "provenance": {
            "acquisition_method": "curated fixture",
            "source_reference": "synthetic://fixture",
            "review_date": "2026-10-13",
            "review_status": "approved",
        },
        "preprocessing": {"tool_version": "fixture-1", "transformations": []},
    }


def test_audit_reports_label_coverage_and_delta_distribution():
    rows = [
        record(
            "train-1", "bank-a", "train",
            [{"start_sec": 0.0, "end_sec": 1.0, "midi_note": 60, "lyric": "a", "voiced": True}],
            [
                {"time_sec": 0.2, "delta_semitones": 0.0},
                {"time_sec": 0.8, "delta_semitones": 0.5},
                {"time_sec": 1.5, "delta_semitones": 1.0},
            ],
        ),
        record(
            "validation-1", "bank-b", "validation",
            [{"start_sec": 0.0, "end_sec": 1.0, "midi_note": 84, "lyric": "i", "voiced": True}],
            [{"time_sec": 0.5, "delta_semitones": -0.25}],
        ),
        record(
            "test-1", "bank-c", "test",
            [{"start_sec": 0.0, "end_sec": 1.0, "midi_note": 48, "lyric": "u", "voiced": True}],
            [{"time_sec": 0.5, "delta_semitones": 0.25}],
        ),
    ]
    # The production CLI performs this gate before auditing.
    summary = validate_jsonl_from_rows(rows)
    report = audit_dataset(rows)

    assert summary["status"] == "valid"
    assert report["status"] == "audited"
    assert report["raw_labels"] == 5
    assert report["usable_labels"] == 4
    assert report["label_usage"]["labels_without_voiced_note"] == 1
    assert report["label_coverage_ratio"] == 0.8
    assert report["by_split"]["train"]["zero_delta_labels"] == 1
    assert report["by_split"]["train"]["nonzero_delta_labels"] == 1
    assert report["by_voicebank"]["bank-a"]["records_with_usable_labels"] == 1
    assert report["by_midi_range"]["midi_72_83"]["usable_labels"] == 0


def validate_jsonl_from_rows(rows):
    # Use the same manifest validator without introducing an audio dependency.
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "manifest.jsonl"
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        return validate_jsonl(path, require_labeled=True)
