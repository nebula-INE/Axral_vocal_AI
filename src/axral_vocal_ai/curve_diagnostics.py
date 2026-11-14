"""Diagnostics for experimental pitch-delta curves; never changes proposals."""
from __future__ import annotations

import math
from typing import Any, Iterable

from .contracts import PitchDeltaPoint


def audit_pitch_curve(
    points: Iterable[PitchDeltaPoint | dict[str, Any]],
    *,
    max_adjacent_jump_semitones: float = 1.0,
    max_slope_semitones_per_sec: float = 12.0,
) -> dict[str, Any]:
    """Summarize local discontinuities in one note's ordered proposal curve.

    Points must belong to the same note and be supplied in chronological order.
    This function is diagnostic only: it does not smooth, clamp, reject, or edit
    any proposal. Thresholds are review flags, not perceptual-quality standards.
    """
    thresholds = {
        "max_adjacent_jump_semitones": max_adjacent_jump_semitones,
        "max_slope_semitones_per_sec": max_slope_semitones_per_sec,
    }
    for name, value in thresholds.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{name} must be numeric")
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and greater than zero")

    normalized: list[tuple[float, float]] = []
    for index, point in enumerate(points):
        if isinstance(point, PitchDeltaPoint):
            time_sec, delta = point.time_sec, point.delta_semitones
        elif isinstance(point, dict):
            time_sec, delta = point.get("time_sec"), point.get("delta_semitones")
        else:
            raise TypeError(f"point {index} must be PitchDeltaPoint or a mapping")
        for name, value in (("time_sec", time_sec), ("delta_semitones", delta)):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"point {index} {name} must be numeric")
            if not math.isfinite(value):
                raise ValueError(f"point {index} {name} must be finite")
        if normalized and time_sec <= normalized[-1][0]:
            raise ValueError("points must have strictly increasing time_sec")
        normalized.append((float(time_sec), float(delta)))

    jumps: list[dict[str, float | int]] = []
    max_jump = 0.0
    max_slope = 0.0
    total_variation = 0.0
    for index, ((time_a, delta_a), (time_b, delta_b)) in enumerate(
        zip(normalized, normalized[1:])
    ):
        jump = abs(delta_b - delta_a)
        slope = jump / (time_b - time_a)
        max_jump = max(max_jump, jump)
        max_slope = max(max_slope, slope)
        total_variation += jump
        if jump > max_adjacent_jump_semitones or slope > max_slope_semitones_per_sec:
            jumps.append({
                "segment_index": index,
                "start_sec": time_a,
                "end_sec": time_b,
                "jump_semitones": jump,
                "slope_semitones_per_sec": slope,
            })

    return {
        "status": "audited",
        "point_count": len(normalized),
        "segment_count": max(0, len(normalized) - 1),
        "max_adjacent_jump_semitones": max_jump,
        "max_slope_semitones_per_sec": max_slope,
        "total_variation_semitones": total_variation,
        "flagged_segment_count": len(jumps),
        "flagged_segments": jumps,
        "thresholds": thresholds,
        "limitations": [
            "Points must describe one note; do not compare across note boundaries.",
            "Flags are heuristic diagnostics, not proof of audible artifacts or naturalness.",
            "The audit does not modify or smooth pitch proposals.",
        ],
    }
