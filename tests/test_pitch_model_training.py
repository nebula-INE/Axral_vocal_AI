import pytest

from axral_vocal_ai.pitch_model import examples_from_records, fit_ridge, mean_absolute_error
from axral_vocal_ai.training_data import validate_records


def record(record_id, bank, split, start, end, midi, targets):
    return {
        "schema_version": 1, "record_id": record_id, "source_id": "synthetic-source",
        "permission_status": "approved", "license_id": "SYNTHETIC-TEST-ONLY",
        "voicebank_id": bank, "split": split,
        "input": {"notes": [{"start_sec": start, "end_sec": end, "midi_note": midi,
                             "lyric": "synthetic", "voiced": True}]},
        "target": {"kind": "pitch_delta_semitones",
                   "points": [{"time_sec": t, "delta_semitones": delta} for t, delta in targets],
                   "label_source": "synthetic_fixture", "confidence": 1.0},
        "provenance": {"acquisition_method": "synthetic", "source_reference": "synthetic://fixture",
                       "review_date": "2026-10-11", "review_status": "approved"},
        "preprocessing": {"tool_version": "test-1", "transformations": []},
    }


def synthetic_records():
    # Distinct banks stay isolated by split. Synthetic values validate plumbing only.
    return [
        record("train-a", "bank-a", "train", 0.0, 1.0, 60,
               [(0.0, 0.0), (0.5, 0.25), (1.0, 0.5)]),
        record("train-b", "bank-d", "train", 0.0, 1.0, 72,
               [(0.0, 0.1), (0.5, 0.35), (1.0, 0.6)]),
        record("valid", "bank-b", "validation", 0.0, 1.0, 65,
               [(0.0, 0.0), (0.5, 0.2), (1.0, 0.4)]),
        record("test", "bank-c", "test", 0.0, 1.0, 67,
               [(0.0, 0.0), (0.5, 0.2), (1.0, 0.4)]),
    ]


def test_training_examples_use_note_context_and_skip_unvoiced_labels():
    rows = synthetic_records()
    rows[0]["input"]["notes"][0]["voiced"] = False
    examples, counts = examples_from_records(rows[:1])
    assert examples == []
    assert counts == {"labels_seen": 3, "labels_used": 0, "labels_without_voiced_note": 3}


def test_ridge_training_is_finite_and_serializable():
    records = synthetic_records()
    validate_records(records, require_labeled=True)
    examples, counts = examples_from_records(records)
    train = [row for row in examples if row.split == "train"]
    validation = [row for row in examples if row.split == "validation"]
    test = [row for row in examples if row.split == "test"]
    model = fit_ridge(train, alpha=1.0)
    assert len(model.weights) == 5
    assert all(value == value and abs(value) != float("inf") for value in model.weights)
    assert mean_absolute_error(validation, model) is not None
    assert mean_absolute_error(test, model) is not None
    assert model.to_dict()["safety"]["production_renderer_integration"] is False
    assert counts["labels_used"] == 12


def test_ridge_rejects_invalid_regularization():
    rows, _ = examples_from_records(synthetic_records())
    with pytest.raises(ValueError, match="alpha"):
        fit_ridge(rows, alpha=-1.0)


def test_ridge_requires_training_examples():
    with pytest.raises(ValueError, match="no usable"):
        fit_ridge([])
