import pytest

from axral_vocal_ai.baseline import mean_absolute_error, zero_delta_baseline
from axral_vocal_ai.contracts import PitchDeltaPoint


def test_zero_delta_baseline_is_deterministic_and_keeps_timestamps() -> None:
    labels = [
        PitchDeltaPoint(0.0, 0.0),
        PitchDeltaPoint(0.1, 0.25),
        PitchDeltaPoint(0.2, -0.5),
    ]

    first = zero_delta_baseline(labels, request_id="synthetic-1")
    second = zero_delta_baseline(labels, request_id="synthetic-1")

    assert first == second
    assert first.status == "ok"
    assert first.request_id == "synthetic-1"
    assert [point.time_sec for point in first.pitch_deltas] == [0.0, 0.1, 0.2]
    assert [point.delta_semitones for point in first.pitch_deltas] == [0.0, 0.0, 0.0]
    assert "not a trained model" in first.warnings[0]


def test_zero_delta_baseline_handles_empty_reference() -> None:
    response = zero_delta_baseline([], request_id="empty")
    assert response.status == "no_change"
    assert response.pitch_deltas == ()
    assert response.request_id == "empty"


def test_mae_is_measured_in_semitones() -> None:
    reference = [
        PitchDeltaPoint(0.0, 0.0),
        PitchDeltaPoint(0.1, 0.25),
        PitchDeltaPoint(0.2, -0.5),
    ]
    predicted = zero_delta_baseline(reference).pitch_deltas
    assert mean_absolute_error(predicted, reference) == pytest.approx(0.25)


def test_mae_rejects_mismatched_lengths_and_timestamps() -> None:
    reference = [PitchDeltaPoint(0.0, 0.1)]
    with pytest.raises(ValueError, match="counts must match"):
        mean_absolute_error([], reference)
    with pytest.raises(ValueError, match="timestamp mismatch"):
        mean_absolute_error([PitchDeltaPoint(0.1, 0.0)], reference)


def test_mae_rejects_empty_reference() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        mean_absolute_error([], [])
