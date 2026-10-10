"""Deterministic, data-free baseline for pitch-expression experiments.

This module proposes semitone deltas only. It does not load audio, train a
model, mutate source notes, or call the VO-SE_vocal renderer.
"""
from __future__ import annotations

from typing import Sequence

from .contracts import PitchDeltaPoint, PitchResponse


def zero_delta_baseline(
    reference_points: Sequence[PitchDeltaPoint],
    request_id: str | None = None,
) -> PitchResponse:
    """Return a zero-semitone proposal at each reference timestamp.

    Timestamps are copied only to make comparison deterministic; target values
    are deliberately ignored. The reference points are evaluation labels, not
    production pitch curves.
    """
    if not reference_points:
        return PitchResponse(
            status="no_change",
            warnings=("No evaluation timestamps were supplied.",),
            request_id=request_id,
        )
    return PitchResponse(
        status="ok",
        pitch_deltas=[
            PitchDeltaPoint(time_sec=point.time_sec, delta_semitones=0.0)
            for point in reference_points
        ],
        warnings=("Deterministic zero-delta baseline; not a trained model.",),
        request_id=request_id,
    )


def mean_absolute_error(
    predicted: Sequence[PitchDeltaPoint],
    reference: Sequence[PitchDeltaPoint],
) -> float:
    """Calculate MAE in semitones after requiring exact timestamp alignment."""
    if not reference:
        raise ValueError("reference points cannot be empty")
    if len(predicted) != len(reference):
        raise ValueError("predicted and reference point counts must match")

    total = 0.0
    for index, (prediction, target) in enumerate(zip(predicted, reference)):
        if prediction.time_sec != target.time_sec:
            raise ValueError(f"timestamp mismatch at index {index}")
        total += abs(prediction.delta_semitones - target.delta_semitones)
    return total / len(reference)
