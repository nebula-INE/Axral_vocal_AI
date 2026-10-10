import pytest

from axral_vocal_ai.contracts import (
    PitchDeltaPoint,
    PitchNote,
    PitchRequest,
    PitchResponse,
)
from axral_vocal_ai.response_validation import (
    PitchResponseValidationError,
    validate_pitch_response,
)


def _request() -> PitchRequest:
    return PitchRequest(
        notes=(
            PitchNote(0.0, 0.5, 60, "あ", voiced=True),
            PitchNote(0.5, 0.75, 62, "休符", voiced=False),
            PitchNote(0.75, 1.0, 64, "い", voiced=None),
        ),
        request_id="req-1",
    )


def test_accepts_points_in_voiced_and_unresolved_note_intervals() -> None:
    request = _request()
    response = PitchResponse(
        status="ok",
        pitch_deltas=(
            PitchDeltaPoint(0.2, 0.5),
            PitchDeltaPoint(0.9, -1.25),
        ),
        request_id="req-1",
    )
    assert validate_pitch_response(request, response) is response


def test_rejects_delta_outside_conservative_bound() -> None:
    response = PitchResponse(
        status="ok",
        pitch_deltas=(PitchDeltaPoint(0.2, 2.01),),
        request_id="req-1",
    )
    with pytest.raises(PitchResponseValidationError, match="safety bound"):
        validate_pitch_response(_request(), response)


def test_rejects_points_in_rest_interval() -> None:
    response = PitchResponse(
        status="ok",
        pitch_deltas=(PitchDeltaPoint(0.6, 0.25),),
        request_id="req-1",
    )
    with pytest.raises(PitchResponseValidationError, match="outside eligible"):
        validate_pitch_response(_request(), response)


def test_rejects_points_outside_all_note_intervals() -> None:
    response = PitchResponse(
        status="ok",
        pitch_deltas=(PitchDeltaPoint(1.2, 0.25),),
        request_id="req-1",
    )
    with pytest.raises(PitchResponseValidationError, match="outside eligible"):
        validate_pitch_response(_request(), response)


def test_rejects_request_id_mismatch() -> None:
    response = PitchResponse(
        status="ok",
        pitch_deltas=(PitchDeltaPoint(0.2, 0.25),),
        request_id="different-request",
    )
    with pytest.raises(PitchResponseValidationError, match="request_id"):
        validate_pitch_response(_request(), response)


def test_rejects_missing_response_request_id_when_request_has_one() -> None:
    response = PitchResponse(
        status="ok",
        pitch_deltas=(PitchDeltaPoint(0.2, 0.25),),
    )
    with pytest.raises(PitchResponseValidationError, match="request_id"):
        validate_pitch_response(_request(), response)


@pytest.mark.parametrize("status", ["no_change", "rejected"])
def test_non_mutating_statuses_are_passed_through(status: str) -> None:
    response = PitchResponse(status=status, request_id="req-1")
    assert validate_pitch_response(_request(), response) is response


def test_rejects_invalid_policy_parameters() -> None:
    response = PitchResponse(status="ok", request_id="req-1")
    with pytest.raises(ValueError, match="greater than zero"):
        validate_pitch_response(_request(), response, max_abs_delta_semitones=0)
    with pytest.raises(ValueError, match="non-negative"):
        validate_pitch_response(_request(), response, time_tolerance_sec=-1)


def test_allows_small_boundary_rounding_tolerance() -> None:
    response = PitchResponse(
        status="ok",
        pitch_deltas=(PitchDeltaPoint(-5e-7, 0.1),),
        request_id="req-1",
    )
    assert validate_pitch_response(_request(), response) is response


def test_rejects_point_exactly_at_rest_start_after_voiced_note() -> None:
    # Note intervals share a boundary at 0.5s. The explicit rest must win
    # over the preceding voiced note's inclusive endpoint.
    response = PitchResponse(
        status="ok",
        pitch_deltas=(PitchDeltaPoint(0.5, 0.25),),
        request_id="req-1",
    )
    with pytest.raises(PitchResponseValidationError, match="outside eligible"):
        validate_pitch_response(_request(), response)


def test_rejects_point_within_tolerance_of_rest_boundary() -> None:
    response = PitchResponse(
        status="ok",
        pitch_deltas=(PitchDeltaPoint(0.5000005, 0.25),),
        request_id="req-1",
    )
    with pytest.raises(PitchResponseValidationError, match="outside eligible"):
        validate_pitch_response(_request(), response)
