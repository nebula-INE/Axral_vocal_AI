"""Deterministic metadata-only builder for reviewed pitch-delta labels.

Input pitch values must already be expressed in semitones on the same absolute
seconds grid. This module does not estimate F0, resample, interpolate, or read audio.
"""
from __future__ import annotations

import math
from typing import Any, Iterable, Mapping

MAX_DELTA_SEMITONES = 2.0


class PitchLabelError(ValueError):
    """Raised when reference/target pitch tracks cannot safely form labels."""


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PitchLabelError(f"{field} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise PitchLabelError(f"{field} must be finite")
    return number


def _normalize_track(
    points: Iterable[Mapping[str, Any]], name: str, min_confidence: float | None
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    previous_time = -math.inf
    for index, point in enumerate(points):
        where = f"{name}[{index}]"
        if not isinstance(point, Mapping):
            raise PitchLabelError(f"{where} must be an object")
        if "time_sec" not in point or "voiced" not in point:
            raise PitchLabelError(f"{where} requires time_sec and voiced")
        time_sec = _finite_number(point["time_sec"], f"{where}.time_sec")
        if time_sec < 0 or time_sec <= previous_time:
            raise PitchLabelError(f"{where}.time_sec must be non-negative and strictly increasing")
        if not isinstance(point["voiced"], bool):
            raise PitchLabelError(f"{where}.voiced must be bool")
        confidence = point.get("confidence")
        if confidence is not None:
            confidence = _finite_number(confidence, f"{where}.confidence")
            if not 0.0 <= confidence <= 1.0:
                raise PitchLabelError(f"{where}.confidence must be in [0, 1]")
        if min_confidence is not None and point["voiced"] and confidence is None:
            raise PitchLabelError(
                f"{where}.confidence is required when min_confidence is configured"
            )
        pitch = None
        if point["voiced"]:
            if "pitch_semitones" not in point:
                raise PitchLabelError(f"{where}.pitch_semitones is required for voiced points")
            pitch = _finite_number(point["pitch_semitones"], f"{where}.pitch_semitones")
        normalized.append({
            "time_sec": time_sec,
            "voiced": point["voiced"],
            "pitch_semitones": pitch,
            "confidence": confidence,
        })
        previous_time = time_sec
    return normalized


def build_pitch_delta_labels(
    reference_points: Iterable[Mapping[str, Any]],
    target_points: Iterable[Mapping[str, Any]],
    *,
    min_confidence: float | None = None,
) -> list[dict[str, float]]:
    """Build target-minus-reference labels on an identical time grid.

    Each point has time_sec, voiced, and (when voiced) pitch_semitones.
    Optional confidence must be in [0, 1]. If min_confidence is provided,
    every voiced point must have confidence; a pair is omitted when either
    confidence is below the threshold or either side is unvoiced. No
    interpolation is performed across omitted regions. Deltas outside the
    +/-2-semitone training contract are rejected rather than clipped.
    """
    if min_confidence is not None:
        min_confidence = _finite_number(min_confidence, "min_confidence")
        if not 0.0 <= min_confidence <= 1.0:
            raise PitchLabelError("min_confidence must be in [0, 1]")

    reference = _normalize_track(reference_points, "reference_points", min_confidence)
    target = _normalize_track(target_points, "target_points", min_confidence)
    if len(reference) != len(target):
        raise PitchLabelError("reference and target tracks must use the same time grid")

    labels: list[dict[str, float]] = []
    for index, (ref, tgt) in enumerate(zip(reference, target)):
        if ref["time_sec"] != tgt["time_sec"]:
            raise PitchLabelError(
                f"time-grid mismatch at index {index}: "
                f"{ref['time_sec']} != {tgt['time_sec']}"
            )
        if not ref["voiced"] or not tgt["voiced"]:
            continue
        if min_confidence is not None and (
            ref["confidence"] < min_confidence or tgt["confidence"] < min_confidence
        ):
            continue
        delta = tgt["pitch_semitones"] - ref["pitch_semitones"]
        if not -MAX_DELTA_SEMITONES <= delta <= MAX_DELTA_SEMITONES:
            raise PitchLabelError(
                f"delta at time {ref['time_sec']} is outside +/-{MAX_DELTA_SEMITONES} semitones"
            )
        labels.append({"time_sec": ref["time_sec"], "delta_semitones": delta})
    return labels



def make_training_target(
    labels: Iterable[Mapping[str, Any]],
    *,
    label_source: str,
    confidence: float | None = None,
) -> dict[str, Any]:
    """Wrap reviewed label points in the manifest's training target schema.

    This is the bridge between :func:`build_pitch_delta_labels` and
    `training_data.validate_record`. It only packages metadata; callers remain
    responsible for source rights, review evidence, and manifest provenance.
    Empty labels are rejected because the manifest training schema requires at
    least one usable target point.
    """
    if not isinstance(label_source, str) or not label_source.strip():
        raise PitchLabelError("label_source must be a non-empty string")

    normalized_confidence: float | None = None
    if confidence is not None:
        normalized_confidence = _finite_number(confidence, "confidence")
        if not 0.0 <= normalized_confidence <= 1.0:
            raise PitchLabelError("confidence must be in [0, 1]")

    normalized_labels: list[dict[str, float]] = []
    previous_time = -math.inf
    for index, label in enumerate(labels):
        where = f"labels[{index}]"
        if not isinstance(label, Mapping):
            raise PitchLabelError(f"{where} must be an object")
        if "time_sec" not in label or "delta_semitones" not in label:
            raise PitchLabelError(f"{where} requires time_sec and delta_semitones")
        time_sec = _finite_number(label["time_sec"], f"{where}.time_sec")
        delta = _finite_number(label["delta_semitones"], f"{where}.delta_semitones")
        if time_sec < 0.0 or time_sec <= previous_time:
            raise PitchLabelError(
                f"{where}.time_sec must be non-negative and strictly increasing"
            )
        if not -MAX_DELTA_SEMITONES <= delta <= MAX_DELTA_SEMITONES:
            raise PitchLabelError(
                f"{where}.delta_semitones must be within "
                f"+/-{MAX_DELTA_SEMITONES} semitones"
            )
        normalized_labels.append({"time_sec": time_sec, "delta_semitones": delta})
        previous_time = time_sec

    if not normalized_labels:
        raise PitchLabelError("labels must contain at least one usable point")

    target: dict[str, Any] = {
        "kind": "pitch_delta_semitones",
        "points": normalized_labels,
        "label_source": label_source.strip(),
    }
    if normalized_confidence is not None:
        target["confidence"] = normalized_confidence
    return target
