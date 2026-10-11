import math

import pytest

from axral_vocal_ai.pitch_model import (
    _features_for_time,
    examples_from_records,
    fit_ridge,
    mean_absolute_error,
    zero_baseline_mae,
)
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


def test_adjacent_note_boundary_belongs_to_following_note():
    notes = [
        {"start_sec": 0.0, "end_sec": 1.0, "midi_note": 60, "voiced": True},
        {"start_sec": 1.0, "end_sec": 2.0, "midi_note": 72, "voiced": True},
    ]
    features = _features_for_time(notes, 1.0)
    assert features is not None
    assert features[1] == pytest.approx(72 / 127)
    assert features[2] == 0.0


def test_terminal_note_endpoint_is_kept():
    notes = [{"start_sec": 0.0, "end_sec": 1.0, "midi_note": 60, "voiced": True}]
    features = _features_for_time(notes, 1.0)
    assert features is not None
    assert features[2] == 1.0


def test_boundary_into_unvoiced_note_is_not_assigned_to_previous_note():
    notes = [
        {"start_sec": 0.0, "end_sec": 1.0, "midi_note": 60, "voiced": True},
        {"start_sec": 1.0, "end_sec": 2.0, "midi_note": 0, "voiced": False},
    ]
    assert _features_for_time(notes, 1.0) is None


def test_ridge_training_is_finite_and_serializable():
    records = synthetic_records()
    validate_records(records, require_labeled=True)
    examples, counts = examples_from_records(records)
    train = [row for row in examples if row.split == "train"]
    validation = [row for row in examples if row.split == "validation"]
    test = [row for row in examples if row.split == "test"]
    model = fit_ridge(train, alpha=1.0)
    assert len(model.weights) == 5
    assert all(math.isfinite(value) for value in model.weights)
    assert mean_absolute_error(validation, model) is not None
    assert mean_absolute_error(test, model) is not None
    assert model.to_dict()["safety"]["production_renderer_integration"] is False
    assert counts["labels_used"] == 12


def test_zero_delta_baseline_and_improvement_metric():
    rows, _ = examples_from_records(synthetic_records())
    validation = [row for row in rows if row.split == "validation"]
    model = fit_ridge([row for row in rows if row.split == "train"], alpha=1.0)
    baseline = zero_baseline_mae(validation)
    measured = mean_absolute_error(validation, model)
    assert baseline is not None and measured is not None
    assert math.isfinite(baseline)
    assert baseline == pytest.approx(sum(abs(row.target) for row in validation) / len(validation))


def test_model_evaluation_reports_signed_baseline_improvement():
    rows, _ = examples_from_records(synthetic_records())
    validation = [row for row in rows if row.split == "validation"]
    model = fit_ridge([row for row in rows if row.split == "train"], alpha=1.0)

    metrics = compare_with_zero_baseline(validation, model)

    assert metrics["mae_semitones"] == pytest.approx(mean_absolute_error(validation, model))
    assert metrics["zero_delta_baseline_mae_semitones"] == pytest.approx(
        zero_baseline_mae(validation)
    )
    assert metrics["mae_improvement_over_zero_baseline_semitones"] == pytest.approx(
        metrics["zero_delta_baseline_mae_semitones"] - metrics["mae_semitones"]
    )
    baseline = metrics["zero_delta_baseline_mae_semitones"]
    if baseline and baseline > 0:
        assert metrics["relative_mae_improvement_over_zero_baseline"] == pytest.approx(
            metrics["mae_improvement_over_zero_baseline_semitones"] / baseline
        )
    else:
        assert metrics["relative_mae_improvement_over_zero_baseline"] is None


def test_zero_delta_baseline_empty_and_non_finite_target():
    assert zero_baseline_mae([]) is None
    rows, _ = examples_from_records(synthetic_records())
    rows[0] = rows[0].__class__(
        features=rows[0].features, target=float("nan"), record_id=rows[0].record_id,
        voicebank_id=rows[0].voicebank_id, split=rows[0].split,
    )
    with pytest.raises(ValueError, match="finite"):
        zero_baseline_mae(rows)


def test_predict_rejects_non_finite_features():
    rows, _ = examples_from_records(synthetic_records())
    model = fit_ridge([row for row in rows if row.split == "train"])
    with pytest.raises(ValueError, match="finite"):
        model.predict_features([1.0, 0.5, float("nan"), 0.0, 1.0])


def test_ridge_rejects_invalid_regularization():
    rows, _ = examples_from_records(synthetic_records())
    with pytest.raises(ValueError, match="alpha"):
        fit_ridge(rows, alpha=-1.0)


def test_ridge_requires_training_examples():
    with pytest.raises(ValueError, match="no usable"):
        fit_ridge([])
