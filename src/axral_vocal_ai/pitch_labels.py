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
