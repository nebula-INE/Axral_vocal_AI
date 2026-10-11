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
FEATURE_NAMES = ("bias", "midi_normalized", "note_phase", "phase_squared", "duration_seconds")


@dataclass(frozen=True)
class TrainingExample:
    features: tuple[float, ...]
    target: float
    record_id: str
    voicebank_id: str
    split: str


def _features_for_time(notes: list[dict[str, Any]], time_sec: float) -> tuple[float, ...] | None:
    for note in notes:
        start = float(note["start_sec"])
        end = float(note["end_sec"])
        if note.get("voiced") is False:
            continue
        if start <= time_sec <= end:
            duration = end - start
            phase = 0.0 if duration <= 0.0 else min(1.0, max(0.0, (time_sec - start) / duration))
            midi = float(note["midi_note"])
            return (1.0, midi / 127.0, phase, phase * phase, duration)
    return None


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
        result = sum(w * value for w, value in zip(self.weights, values))
        if not np.isfinite(result):
            raise ValueError("model produced a non-finite prediction")
        return float(result)

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
    rows = list(examples)
    if not rows:
        return None
    errors = [abs(model.predict_features(row.features) - row.target) for row in rows]
    return float(sum(errors) / len(errors))
