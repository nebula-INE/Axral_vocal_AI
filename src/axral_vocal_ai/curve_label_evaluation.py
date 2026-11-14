"""Evaluate sampled pitch curves against timestamped human/reference labels.

Evaluation is metadata-only. Targets must be reviewed, rights-cleared pitch-delta
labels in semitones; no audio is loaded and no renderer is invoked.
"""
from __future__ import annotations

import math
from typing import Any, Iterable

from .contracts import PitchRequest, PitchResponse
from .pitch_model import MAX_PREDICTION_DELTA_SEMITONES
from .response_validation import validate_pitch_response


def evaluate_pitch_curve_against_labels(
    request: PitchRequest,
    response: PitchResponse,
    target_points: Iterable[dict[str, float]],
) -> dict[str, Any]:
    """Score a sampled response at label timestamps using within-note interpolation.

    Each target is {"time_sec": ..., "delta_semitones": ...}. Labels are evaluated
    only when they lie strictly inside exactly one eligible, non-overlapping note
    and are bracketed by response samples belonging to that same note. The
    function deliberately does not extrapolate to note edges or across notes.
    """
    if not isinstance(request, PitchRequest):
        raise TypeError("request must be a PitchRequest")
    if not isinstance(response, PitchResponse):
        raise TypeError("response must be a PitchResponse")
    validate_pitch_response(
        request,
        response,
        max_abs_delta_semitones=MAX_PREDICTION_DELTA_SEMITONES,
    )

    notes: list[tuple[int, Any]] = []
    for index, note in enumerate(request.notes):
        if note.voiced is False or note.end_sec <= note.start_sec:
            continue
        if any(
            other_index != index
            and max(note.start_sec, other.start_sec) < min(note.end_sec, other.end_sec)
            for other_index, other in enumerate(request.notes)
        ):
            continue
        notes.append((index, note))

    grouped: dict[int, list[Any]] = {index: [] for index, _ in notes}
    for point in response.pitch_deltas:
        matches = [
            index for index, note in notes
            if note.start_sec < point.time_sec < note.end_sec
        ]
        if len(matches) != 1:
            raise ValueError("response point cannot be mapped to exactly one eligible note")
        grouped[matches[0]].append(point)
    for points in grouped.values():
        points.sort(key=lambda point: point.time_sec)

    evaluated: list[dict[str, float | int]] = []
    skipped: list[dict[str, Any]] = []
    seen_times: set[float] = set()
    for label_index, raw in enumerate(target_points):
        if not isinstance(raw, dict):
            raise ValueError(f"target point {label_index} must be an object")
        time_sec = raw.get("time_sec")
        target = raw.get("delta_semitones")
        if (
            isinstance(time_sec, bool) or not isinstance(time_sec, (int, float))
            or not math.isfinite(float(time_sec))
            or isinstance(target, bool) or not isinstance(target, (int, float))
            or not math.isfinite(float(target))
            or abs(float(target)) > MAX_PREDICTION_DELTA_SEMITONES
        ):
            raise ValueError(f"target point {label_index} has invalid time or delta")
        time_sec, target = float(time_sec), float(target)
        if time_sec in seen_times:
            raise ValueError("target timestamps must be unique")
        seen_times.add(time_sec)
        matches = [
            (index, note) for index, note in notes
            if note.start_sec < time_sec < note.end_sec
        ]
        if len(matches) != 1:
            skipped.append({"label_index": label_index, "reason": "not inside exactly one eligible note"})
            continue
        note_index, _ = matches[0]
        points = grouped[note_index]
        left = next((point for point in reversed(points) if point.time_sec <= time_sec), None)
        right = next((point for point in points if point.time_sec >= time_sec), None)
        if left is None or right is None:
            skipped.append({"label_index": label_index, "reason": "not bracketed by samples within the same note"})
            continue
        if left.time_sec == right.time_sec:
            prediction = left.delta_semitones
        else:
            fraction = (time_sec - left.time_sec) / (right.time_sec - left.time_sec)
            prediction = left.delta_semitones + fraction * (right.delta_semitones - left.delta_semitones)
        evaluated.append({
            "label_index": label_index,
            "note_index": note_index,
            "time_sec": time_sec,
            "target_delta_semitones": target,
            "predicted_delta_semitones": prediction,
            "absolute_error_semitones": abs(prediction - target),
        })

    count = len(evaluated)
    model_mae = (
        sum(float(row["absolute_error_semitones"]) for row in evaluated) / count
        if count else None
    )
    baseline_mae = (
        sum(abs(float(row["target_delta_semitones"])) for row in evaluated) / count
        if count else None
    )
    improvement = baseline_mae - model_mae if baseline_mae is not None and model_mae is not None else None
    relative = improvement / baseline_mae if improvement is not None and baseline_mae else None
    return {
        "status": "evaluated" if count else "insufficient_coverage",
        "labels_seen": count + len(skipped),
        "labels_evaluated": count,
        "labels_skipped": len(skipped),
        "skipped_labels": skipped,
        "mae_semitones": model_mae,
        "zero_delta_baseline_mae_semitones": baseline_mae,
        "mae_improvement_over_zero_baseline_semitones": improvement,
        "relative_mae_improvement_over_zero_baseline": relative,
        "evaluated_points": evaluated,
        "limitations": [
            "Labels not bracketed by samples within the same note are skipped; no extrapolation is performed.",
            "Linear interpolation scores the emitted sample curve, not the underlying model at unsampled timestamps.",
            "Metrics do not establish perceptual quality; review licensed labels and listen to held-out results.",
        ],
    }
