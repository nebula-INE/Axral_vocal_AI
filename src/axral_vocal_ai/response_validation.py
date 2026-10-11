"""Safety checks for AI-proposed pitch deltas.

This module validates proposals before any renderer adapter sees them. It does
not clamp, resample, apply, or otherwise mutate source notes or pitch curves.
"""
from __future__ import annotations

import math

from .contracts import PitchRequest, PitchResponse


class PitchResponseValidationError(ValueError):
    """Raised when an AI proposal is unsafe or inconsistent with its request."""


def validate_pitch_response(
    request: PitchRequest,
    response: PitchResponse,
    *,
    max_abs_delta_semitones: float = 2.0,
    time_tolerance_sec: float = 1e-6,
) -> PitchResponse:
    """Validate a pitch proposal against the request without modifying either.

    A proposal point must fall inside a note interval that is not explicitly
    marked unvoiced/rest. Unresolved notes (voiced=None) remain eligible because
    alias resolution may intentionally be unavailable to a caller. The default
    ±2-semitone bound is a conservative MVP guardrail, not a claim about the
    full expressive range of a future model.

    If the request supplies a correlation ID, the response must echo that exact
    ID. Invalid proposals are rejected rather than silently clamped. The caller
    should keep the original pitch path when this function raises.
    """
    if not math.isfinite(max_abs_delta_semitones) or max_abs_delta_semitones <= 0:
        raise ValueError("max_abs_delta_semitones must be finite and greater than zero")
    if not math.isfinite(time_tolerance_sec) or time_tolerance_sec < 0:
        raise ValueError("time_tolerance_sec must be finite and non-negative")

    if request.request_id is not None and response.request_id != request.request_id:
        raise PitchResponseValidationError(
            "response request_id is missing or does not match request"
        )

    if response.status == "rejected":
        if response.pitch_deltas:
            raise PitchResponseValidationError("rejected response cannot contain pitch deltas")
        return response
    if response.status == "no_change":
        if response.pitch_deltas:
            raise PitchResponseValidationError("no_change response cannot contain pitch deltas")
        return response
    if response.status != "ok":
        raise PitchResponseValidationError(f"unsupported response status: {response.status}")

    # A zero-duration voiced note has no interval to carry a pitch proposal.
    # Keep zero-duration explicit rests in the rest check below so they still
    # take precedence at an exact shared boundary.
    eligible = tuple(
        note for note in request.notes
        if note.voiced is not False and note.end_sec > note.start_sec
    )
    for index, point in enumerate(response.pitch_deltas):
        if abs(point.delta_semitones) > max_abs_delta_semitones:
            raise PitchResponseValidationError(
                f"pitch delta at index {index} exceeds the configured "
                f"±{max_abs_delta_semitones:g}-semitone safety bound"
            )
        # Explicit rests take precedence at shared note boundaries. Otherwise,
        # an inclusive end on the preceding voiced note could accidentally admit
        # a point exactly at the start of a following rest.
        in_rest = any(
            note.voiced is False
            and note.start_sec - time_tolerance_sec <= point.time_sec
            <= note.end_sec + time_tolerance_sec
            for note in request.notes
        )
        covered = any(
            note.start_sec - time_tolerance_sec <= point.time_sec
            <= note.end_sec + time_tolerance_sec
            for note in eligible
        )
        if in_rest or not covered:
            raise PitchResponseValidationError(
                f"pitch delta at index {index} falls outside eligible note intervals"
            )
    return response
