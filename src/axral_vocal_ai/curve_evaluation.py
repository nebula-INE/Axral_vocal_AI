"""Per-note diagnostics for experimental pitch proposal responses.

This module reports heuristic discontinuities only; it never changes proposals.
"""
from __future__ import annotations

from typing import Any

from .contracts import PitchRequest, PitchResponse
from .curve_diagnostics import audit_pitch_curve
from .pitch_model import MAX_PREDICTION_DELTA_SEMITONES
from .response_validation import validate_pitch_response


def audit_pitch_response_curves(
    request: PitchRequest,
    response: PitchResponse,
    *,
    max_adjacent_jump_semitones: float = 1.0,
    max_slope_semitones_per_sec: float = 12.0,
) -> dict[str, Any]:
    """Audit response samples grouped by eligible note, never across boundaries.

    The response is validated against its request first. Notes overlapping any
    other interval are excluded using the inference runtime's conservative rule.
    Every response point must map to exactly one eligible note interior.
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

    eligible: list[tuple[int, Any]] = []
    skipped_notes: list[dict[str, Any]] = []
    for index, note in enumerate(request.notes):
        if note.voiced is False:
            skipped_notes.append({"note_index": index, "reason": "unvoiced or rest"})
            continue
        if note.end_sec <= note.start_sec:
            skipped_notes.append({"note_index": index, "reason": "zero-duration interval"})
            continue
        overlaps = any(
            other_index != index
            and max(note.start_sec, other.start_sec) < min(note.end_sec, other.end_sec)
            for other_index, other in enumerate(request.notes)
        )
        if overlaps:
            skipped_notes.append({"note_index": index, "reason": "overlapping note intervals"})
            continue
        eligible.append((index, note))

    grouped = {index: [] for index, _ in eligible}
    unmapped = 0
    for point in response.pitch_deltas:
        matches = [
            index
            for index, note in eligible
            if note.start_sec < point.time_sec < note.end_sec
        ]
        if len(matches) != 1:
            unmapped += 1
            continue
        grouped[matches[0]].append(point)

    if unmapped:
        raise ValueError(
            f"{unmapped} response point(s) could not be mapped to exactly one note interior"
        )

    per_note: dict[str, Any] = {}
    for index, note in eligible:
        points = grouped[index]
        per_note[str(index)] = {
            "midi_note": note.midi_note,
            "start_sec": note.start_sec,
            "end_sec": note.end_sec,
            "diagnostics": audit_pitch_curve(
                points,
                max_adjacent_jump_semitones=max_adjacent_jump_semitones,
                max_slope_semitones_per_sec=max_slope_semitones_per_sec,
            ),
        }

    return {
        "status": "audited",
        "response_status": response.status,
        "note_count": len(request.notes),
        "eligible_note_count": len(eligible),
        "skipped_notes": skipped_notes,
        "per_note": per_note,
        "flagged_segment_count": sum(
            row["diagnostics"]["flagged_segment_count"]
            for row in per_note.values()
        ),
        "limitations": [
            "Diagnostics are heuristic review signals, not proof of audible artifacts or naturalness.",
            "Only proposal points are analyzed; this does not evaluate reference audio or label correctness.",
            "No proposals are modified, smoothed, clamped, rejected, or applied to a renderer.",
        ],
    }
