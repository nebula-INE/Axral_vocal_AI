"""Experimental, metadata-only pitch-delta regression model.

This model proposes semitone deltas from note context. It does not read audio,
modify projects, or connect to the VO-SE_vocal renderer. It is an MVP for
validating a reproducible training loop, not a musically validated model.
"""
from __future__ import annotations

from dataclasses import dataclass
import heapq
from typing import Any, Iterable

import numpy as np

FEATURE_VERSION = 1
MAX_PREDICTION_DELTA_SEMITONES = 2.0
FEATURE_NAMES = ("bias", "midi_normalized", "note_phase", "phase_squared", "duration_seconds")

# Bound the experimental MVP before constructing dense NumPy matrices.
MAX_TRAINING_EXAMPLES = 250_000
MAX_TRAINING_LABEL_POINTS = 1_000_000


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
        return _note_features(active_notes[0], time_sec)

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
    return _note_features(note, time_sec, endpoint=True)



def _note_features(
    note: dict[str, Any],
    time_sec: float,
    *,
    endpoint: bool = False,
) -> tuple[float, ...]:
    start = float(note["start_sec"])
    end = float(note["end_sec"])
    duration = end - start
    phase = 1.0 if endpoint else min(1.0, max(0.0, (time_sec - start) / duration))
    midi = float(note["midi_note"])
    return (1.0, midi / 127.0, phase, phase * phase, duration)


def _features_for_sorted_points(
    notes: list[dict[str, Any]],
    points: Iterable[dict[str, Any]],
) -> Iterable[tuple[float, ...] | None]:
    """Resolve sorted labels with a sweep line instead of rescanning every note.

    Manifest validation guarantees notes are sorted by start time and label
    points are strictly increasing. The active set therefore advances only
    when a note starts or ends, keeping the mapping O((notes + labels) log notes).
    """
    next_note = 0
    active: dict[int, dict[str, Any]] = {}
    endings: list[tuple[float, int]] = []

    for point in points:
        time_sec = float(point["time_sec"])
        starts_at_time = False

        ended_at_time: list[dict[str, Any]] = []
        while next_note < len(notes):
            note = notes[next_note]
            start = float(note["start_sec"])
            if start > time_sec:
                break
            if start == time_sec:
                starts_at_time = True
            end = float(note["end_sec"])
            if note.get("voiced") is not False and end > start:
                if end > time_sec:
                    active[next_note] = note
                    heapq.heappush(endings, (end, next_note))
                elif end == time_sec:
                    # This note may have started after the previous label, so
                    # it was never inserted into the active heap.
                    ended_at_time.append(note)
            next_note += 1

        while endings and endings[0][0] <= time_sec:
            end, index = heapq.heappop(endings)
            note = active.pop(index, None)
            if note is not None and end == time_sec:
                ended_at_time.append(note)

        if len(active) > 1:
            yield None
        elif len(active) == 1:
            yield _note_features(next(iter(active.values())), time_sec)
        elif starts_at_time:
            # A note starting at this timestamp wins over endpoint fallback,
            # including when that newly-started note is unvoiced.
            yield None
        elif len(ended_at_time) == 1:
            yield _note_features(ended_at_time[0], time_sec, endpoint=True)
        else:
            yield None

def examples_from_records(
    records: Iterable[dict[str, Any]],
    *,
    max_examples: int = MAX_TRAINING_EXAMPLES,
) -> tuple[list[TrainingExample], dict[str, int]]:
    """Convert a one-pass record stream to bounded per-label examples; no audio is accessed."""
    if isinstance(max_examples, bool) or not isinstance(max_examples, int) or max_examples < 1:
        raise ValueError("max_examples must be a positive integer")
    examples: list[TrainingExample] = []
    counts = {"labels_seen": 0, "labels_used": 0, "labels_without_voiced_note": 0}
    for record in records:
        target = record.get("target")
        if not isinstance(target, dict):
            continue
        notes = record["input"]["notes"]
        points = target["points"]
        points_are_ordered = all(
            float(points[index - 1]["time_sec"]) < float(points[index]["time_sec"])
            for index in range(1, len(points))
        )
        notes_are_ordered = all(
            float(notes[index - 1]["start_sec"]) <= float(notes[index]["start_sec"])
            for index in range(1, len(notes))
        )
        feature_rows = (
            _features_for_sorted_points(notes, points)
            if points_are_ordered and notes_are_ordered
            else (_features_for_time(notes, float(point["time_sec"])) for point in points)
        )
        for point, features in zip(points, feature_rows):
            counts["labels_seen"] += 1
            if counts["labels_seen"] > MAX_TRAINING_LABEL_POINTS:
                raise ValueError(
                    f"training label point limit exceeded ({MAX_TRAINING_LABEL_POINTS})"
                )
            if features is None:
                counts["labels_without_voiced_note"] += 1
                continue
            if len(examples) >= max_examples:
                raise ValueError(f"training example limit exceeded ({max_examples})")
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
