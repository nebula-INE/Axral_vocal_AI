"""Heuristic quality-control flags for reviewed pitch-delta labels.

Flags are prompts for human review, not automatic rejection or proof of bad labels.
This module only inspects manifest metadata; it never opens audio.
"""
from __future__ import annotations

import math
from typing import Any, Iterable

from .pitch_model import MAX_PREDICTION_DELTA_SEMITONES

DEFAULT_MAX_ADJACENT_JUMP_SEMITONES = 1.0
DEFAULT_MAX_SLOPE_SEMITONES_PER_SEC = 12.0
DEFAULT_BOUNDARY_MARGIN_SEMITONES = 0.05


def audit_label_quality(
    records: Iterable[dict[str, Any]],
    *,
    max_adjacent_jump_semitones: float = DEFAULT_MAX_ADJACENT_JUMP_SEMITONES,
    max_slope_semitones_per_sec: float = DEFAULT_MAX_SLOPE_SEMITONES_PER_SEC,
    boundary_margin_semitones: float = DEFAULT_BOUNDARY_MARGIN_SEMITONES,
) -> dict[str, Any]:
    """Return review flags for label coverage, bounds, and within-note jumps.

    Consecutive labels are compared only when both resolve to the same unique,
    voiced, non-zero-duration note. A large change can be musically intentional;
    all thresholds are review heuristics rather than validity criteria.
    """
    thresholds = {
        "max_adjacent_jump_semitones": max_adjacent_jump_semitones,
        "max_slope_semitones_per_sec": max_slope_semitones_per_sec,
        "boundary_margin_semitones": boundary_margin_semitones,
    }
    for name, value in thresholds.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{name} must be numeric")
        if not math.isfinite(value) or value < 0 or (
            name != "boundary_margin_semitones" and value == 0
        ):
            raise ValueError(f"{name} must be finite and in the allowed range")

    per_record: list[dict[str, Any]] = []
    totals = {
        "records": 0,
        "labels_seen": 0,
        "labels_mapped_to_unique_voiced_note": 0,
        "labels_unmapped_or_ambiguous": 0,
        "labels_near_delta_bound": 0,
        "flagged_adjacent_segments": 0,
        "records_with_flags": 0,
    }
    for record in records:
        totals["records"] += 1
        record_id = str(record.get("record_id", f"record_{totals['records']}"))
        notes = record.get("input", {}).get("notes", [])
        target = record.get("target")
        points = target.get("points", []) if isinstance(target, dict) else []
        normalized_notes = []
        for note_index, note in enumerate(notes):
            start, end = float(note["start_sec"]), float(note["end_sec"])
            if note.get("voiced") is False or end <= start:
                continue
            overlaps = any(
                other_index != note_index
                and max(start, float(other["start_sec"])) < min(end, float(other["end_sec"]))
                for other_index, other in enumerate(notes)
            )
            if not overlaps:
                normalized_notes.append((note_index, start, end))

        mapped: list[tuple[float, float, int]] = []
        flags: list[dict[str, Any]] = []
        for point_index, point in enumerate(points):
            time_sec = float(point["time_sec"])
            delta = float(point["delta_semitones"])
            totals["labels_seen"] += 1
            matches = [
                note_index for note_index, start, end in normalized_notes
                if start < time_sec < end
            ]
            if len(matches) != 1:
                totals["labels_unmapped_or_ambiguous"] += 1
                flags.append({
                    "type": "label_not_inside_unique_voiced_note",
                    "label_index": point_index,
                    "time_sec": time_sec,
                    "severity": "review",
                })
            else:
                totals["labels_mapped_to_unique_voiced_note"] += 1
                mapped.append((time_sec, delta, matches[0]))

            distance_to_bound = MAX_PREDICTION_DELTA_SEMITONES - abs(delta)
            if distance_to_bound <= boundary_margin_semitones:
                totals["labels_near_delta_bound"] += 1
                flags.append({
                    "type": "label_near_delta_bound",
                    "label_index": point_index,
                    "time_sec": time_sec,
                    "delta_semitones": delta,
                    "severity": "review",
                })

        for previous, current in zip(mapped, mapped[1:]):
            time_a, delta_a, note_a = previous
            time_b, delta_b, note_b = current
            if note_a != note_b:
                continue
            elapsed = time_b - time_a
            if elapsed <= 0:
                # Strictly increasing timestamps are enforced by the manifest gate.
                continue
            jump = abs(delta_b - delta_a)
            slope = jump / elapsed
            reasons = []
            if jump > max_adjacent_jump_semitones:
                reasons.append("adjacent_jump")
            if slope > max_slope_semitones_per_sec:
                reasons.append("steep_slope")
            if reasons:
                totals["flagged_adjacent_segments"] += 1
                flags.append({
                    "type": "within_note_change",
                    "from_time_sec": time_a,
                    "to_time_sec": time_b,
                    "jump_semitones": jump,
                    "slope_semitones_per_sec": slope,
                    "reasons": reasons,
                    "severity": "review",
                })

        if flags:
            totals["records_with_flags"] += 1
        per_record.append({
            "record_id": record_id,
            "label_count": len(points),
            "flag_count": len(flags),
            "flags": flags,
        })

    return {
        "status": "audited",
        **totals,
        "thresholds": thresholds,
        "records": per_record,
        "limitations": [
            "Flags are heuristic review prompts, not proof that labels are incorrect.",
            "Large within-note changes may be intentional expression or a real transition.",
            "Near-boundary labels may be legitimate; verify annotation conventions and provenance.",
            "This report reads metadata only and does not load audio or assess perceptual quality.",
        ],
    }
