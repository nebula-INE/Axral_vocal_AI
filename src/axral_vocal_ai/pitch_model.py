"""Experimental, metadata-only pitch-delta regression model.

This model proposes semitone deltas from note context. It does not read audio,
modify projects, or connect to the VO-SE_vocal renderer. It is an MVP for
validating a reproducible training loop, not a musically validated model.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np

FEATURE_VERSION = 1
MAX_PREDICTION_DELTA_SEMITONES = 2.0
FEATURE_NAMES = ("bias", "midi_normalized", "note_phase", "phase_squared", "duration_seconds")


@dataclass(frozen=True)
class TrainingExample:
    features: tuple[float, ...]
    target: float
    record_id: str
    voicebank_id: str
    split: str


def _features_for_time(notes: list[dict[str, Any]], time_sec: float) -> tuple[float, ...] | None:
    """Resolve a label to an unambiguous note using [start, end) intervals.

    Labels at shared boundaries belong to a note starting at that timestamp.
    If multiple voiced notes overlap at the label time, the label is skipped
    rather than silently training on whichever note happens to appear first.
    """
    active_notes = [
        note for note in notes
        if note.get("voiced") is not False
        and float(note["end_sec"]) > float(note["start_sec"])
        and float(note["start_sec"]) <= time_sec < float(note["end_sec"])
    ]
    if len(active_notes) > 1:
        return None
    if len(active_notes) == 1:
        note = active_notes[0]
        start = float(note["start_sec"])
        end = float(note["end_sec"])
        duration = end - start
        phase = min(1.0, max(0.0, (time_sec - start) / duration))
        midi = float(note["midi_note"])
        return (1.0, midi / 127.0, phase, phase * phase, duration)

    # Preserve endpoint labels when no note starts at that timestamp. A note
    # beginning there takes precedence even if it is unvoiced.
    if any(float(note["start_sec"]) == time_sec for note in notes):
        return None
    ending_notes = [
        note for note in notes
        if note.get("voiced") is not False
        and float(note["end_sec"]) > float(note["start_sec"])
        and float(note["end_sec"]) == time_sec
    ]
    if len(ending_notes) != 1:
        return None
    note = ending_notes[0]
    duration = float(note["end_sec"]) - float(note["start_sec"])
    midi = float(note["midi_note"])
    return (1.0, midi / 127.0, 1.0, 1.0, duration)


def examples_from_records(records: Iterable[dict[str, Any]]) -> tuple[list[TrainingExample], dict[str, int]]:
    """Convert validated manifest rows to per-label examples; no audio is accessed."""
    examples: list[TrainingExample] = []
    counts = {"labels_seen": 0, "labels_used": 0, "labels_without_voiced_note": 0}
    for record in records:
        target = record.get("target")
        if not isinstance(target, dict):
            continue
        notes = record["input"]["notes"]
        for point in target["points"]:
            counts["labels_seen"] += 1
            features = _features_for_time(notes, float(point["time_sec"]))
            if features is None:
                counts["labels_without_voiced_note"] += 1
                continue
            examples.append(TrainingExample(
                features=features,
                target=float(point["delta_semitones"]),
                record_id=record["record_id"],
                voicebank_id=record["voicebank_id"],
                split=record["split"],
            ))
            counts["labels_used"] += 1
    return examples, counts


@dataclass(frozen=True)
class LinearPitchDeltaModel:
    """Small ridge-regression model serialized as plain JSON metadata/weights."""
    weights: tuple[float, ...]
    feature_version: int = FEATURE_VERSION
    model_type: str = "linear_ridge_pitch_delta"
    target_kind: str = "pitch_delta_semitones"

    def predict_features(self, features: Iterable[float]) -> float:
        values = tuple(float(v) for v in features)
        if len(values) != len(self.weights):
            raise ValueError(f"expected {len(self.weights)} features, got {len(values)}")
        if not all(np.isfinite(value) for value in values):
            raise ValueError("prediction features must be finite")
        result = sum(w * value for w, value in zip(self.weights, values))
        if not np.isfinite(result):
            raise ValueError("model produced a non-finite prediction")
        # Keep experimental proposals inside the same safety envelope enforced
        # for training labels. This does not alter the production renderer.
        bounded = min(MAX_PREDICTION_DELTA_SEMITONES, max(-MAX_PREDICTION_DELTA_SEMITONES, result))
        return float(bounded)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_type": self.model_type,
            "schema_version": 1,
            "feature_version": self.feature_version,
            "feature_names": list(FEATURE_NAMES),
            "target_kind": self.target_kind,
            "weights": list(self.weights),
            "safety": {
                "proposal_only": True,
                "waveform_generation": False,
                "production_renderer_integration": False,
            },
        }


def fit_ridge(examples: Iterable[TrainingExample], alpha: float = 1.0) -> LinearPitchDeltaModel:
    """Fit a deterministic closed-form ridge regressor on supplied train rows."""
    rows = list(examples)
    if not rows:
        raise ValueError("no usable training labels")
    if not np.isfinite(alpha) or alpha < 0:
        raise ValueError("alpha must be finite and non-negative")
    if any(row.split != "train" for row in rows):
        raise ValueError("fit_ridge accepts training-split examples only")
    x = np.asarray([row.features for row in rows], dtype=np.float64)
    y = np.asarray([row.target for row in rows], dtype=np.float64)
    if x.ndim != 2 or x.shape[1] != len(FEATURE_NAMES) or not np.isfinite(x).all():
        raise ValueError("training features are malformed or non-finite")
    if y.ndim != 1 or not np.isfinite(y).all():
        raise ValueError("training targets are malformed or non-finite")
    penalty = np.eye(x.shape[1], dtype=np.float64) * float(alpha)
    penalty[0, 0] = 0.0  # do not regularize the intercept
    try:
        weights = np.linalg.solve(x.T @ x + penalty, x.T @ y)
    except np.linalg.LinAlgError:
        weights = np.linalg.lstsq(x.T @ x + penalty, x.T @ y, rcond=None)[0]
    if not np.isfinite(weights).all():
        raise ValueError("fit produced non-finite weights")
    return LinearPitchDeltaModel(weights=tuple(float(v) for v in weights))


def mean_absolute_error(examples: Iterable[TrainingExample], model: LinearPitchDeltaModel) -> float | None:
    """Mean absolute error for a fitted model; None means no usable examples."""
    rows = list(examples)
    if not rows:
        return None
    errors = [abs(model.predict_features(row.features) - row.target) for row in rows]
    return float(sum(errors) / len(errors))


def zero_baseline_mae(examples: Iterable[TrainingExample]) -> float | None:
    """MAE for a no-correction baseline that predicts zero semitone delta."""
    rows = list(examples)
    if not rows:
        return None
    if not all(np.isfinite(row.target) for row in rows):
        raise ValueError("baseline targets must be finite")
    return float(sum(abs(row.target) for row in rows) / len(rows))


def compare_with_zero_baseline(
    examples: Iterable[TrainingExample], model: LinearPitchDeltaModel
) -> dict[str, float | None]:
    """Report model MAE and signed improvement against the zero-delta baseline.

    Positive improvement means lower error than predicting no correction;
    negative improvement means the fitted model is worse. Relative improvement
    is omitted when the baseline error is zero to avoid division by zero.
    """
    rows = list(examples)
    model_mae = mean_absolute_error(rows, model)
    baseline_mae = zero_baseline_mae(rows)
    improvement = (
        baseline_mae - model_mae
        if baseline_mae is not None and model_mae is not None
        else None
    )
    relative_improvement = (
        improvement / baseline_mae
        if improvement is not None and baseline_mae is not None and baseline_mae > 0
        else None
    )
    return {
        "mae_semitones": model_mae,
        "zero_delta_baseline_mae_semitones": baseline_mae,
        "mae_improvement_over_zero_baseline_semitones": improvement,
        "relative_mae_improvement_over_zero_baseline": relative_improvement,
    }



def evaluate_by_voicebank(
    examples: Iterable[TrainingExample], model: LinearPitchDeltaModel
) -> dict[str, dict[str, float | int | None]]:
    """Report baseline-comparison metrics separately for each voicebank.

    Grouping is diagnostic only; the caller must still enforce voicebank-level
    split isolation before fitting or interpreting held-out metrics.
    """
    grouped: dict[str, list[TrainingExample]] = {}
    for example in examples:
        grouped.setdefault(example.voicebank_id, []).append(example)
    return {
        bank: {
            "examples": len(rows),
            **compare_with_zero_baseline(rows, model),
        }
        for bank, rows in sorted(grouped.items())
    }
