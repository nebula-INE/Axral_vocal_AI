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


@pytest.mark.parametrize("delta", [-2.0, 2.0])
def test_accepts_delta_exactly_at_inclusive_safety_bound(delta: float) -> None:
    response = PitchResponse(
        status="ok",
        pitch_deltas=(PitchDeltaPoint(0.2, delta),),
        request_id="req-1",
    )
    assert validate_pitch_response(_request(), response) is response


def test_rejects_point_exactly_at_rest_end_before_unresolved_note() -> None:
    # The explicit rest wins at both of its boundaries, including when the
    # following unresolved note begins at the same timestamp.
    response = PitchResponse(
        status="ok",
        pitch_deltas=(PitchDeltaPoint(0.75, 0.25),),
        request_id="req-1",
    )
    with pytest.raises(PitchResponseValidationError, match="outside eligible"):
        validate_pitch_response(_request(), response)

@pytest.mark.parametrize("time_sec", [0.25, 0.75])
def test_accepts_exact_voiced_note_boundaries_without_adjacent_rest(
    time_sec: float,
) -> None:
    request = PitchRequest(
        notes=(PitchNote(0.25, 0.75, 60, "あ", voiced=True),),
        request_id="boundary-test",
    )
    response = PitchResponse(
        status="ok",
        pitch_deltas=(PitchDeltaPoint(time_sec, 0.25),),
        request_id="boundary-test",
    )
    assert validate_pitch_response(request, response) is response


@pytest.mark.parametrize("time_sec", [0.249998, 0.750002])
def test_rejects_points_beyond_voiced_boundary_tolerance(time_sec: float) -> None:
    request = PitchRequest(
        notes=(PitchNote(0.25, 0.75, 60, "あ", voiced=True),),
        request_id="boundary-test",
    )
    response = PitchResponse(
        status="ok",
        pitch_deltas=(PitchDeltaPoint(time_sec, 0.25),),
        request_id="boundary-test",
    )
    with pytest.raises(PitchResponseValidationError, match="outside eligible"):
        validate_pitch_response(request, response)


def test_validation_does_not_mutate_list_backed_contract_data() -> None:
    notes = [PitchNote(0.0, 1.0, 60, "あ", voiced=True)]
    points = [PitchDeltaPoint(0.25, 0.5)]
    request = PitchRequest(notes=notes, request_id="immutable-check")
    response = PitchResponse(
        status="ok",
        pitch_deltas=points,
        request_id="immutable-check",
    )

    assert validate_pitch_response(request, response) is response
    assert request.notes is notes
    assert response.pitch_deltas is points
    assert notes == [PitchNote(0.0, 1.0, 60, "あ", voiced=True)]
    assert points == [PitchDeltaPoint(0.25, 0.5)]



@pytest.mark.parametrize("time_sec", [0.5, 0.5000005])
def test_rejects_points_on_zero_duration_voiced_note(time_sec: float) -> None:
    request = PitchRequest(
        notes=(PitchNote(0.5, 0.5, 60, "あ", voiced=True),),
        request_id="zero-duration",
    )
    response = PitchResponse(
        status="ok",
        pitch_deltas=(PitchDeltaPoint(time_sec, 0.25),),
        request_id="zero-duration",
    )
    with pytest.raises(PitchResponseValidationError, match="outside eligible"):
        validate_pitch_response(request, response)


def test_zero_duration_rest_blocks_point_at_exact_boundary() -> None:
    request = PitchRequest(
        notes=(
            PitchNote(0.0, 0.5, 60, "あ", voiced=True),
            PitchNote(0.5, 0.5, 62, "休符", voiced=False),
        ),
        request_id="zero-duration-rest",
    )
    response = PitchResponse(
        status="ok",
        pitch_deltas=(PitchDeltaPoint(0.5, 0.25),),
        request_id="zero-duration-rest",
    )
    with pytest.raises(PitchResponseValidationError, match="outside eligible"):
        validate_pitch_response(request, response)

def test_rejects_pitch_point_for_zero_duration_voiced_note() -> None:
    request = PitchRequest(
        notes=(PitchNote(0.5, 0.5, 60, "あ", voiced=True),),
        request_id="zero-duration",
    )
    response = PitchResponse(
        status="ok",
        pitch_deltas=(PitchDeltaPoint(0.5, 0.25),),
        request_id="zero-duration",
    )
    with pytest.raises(PitchResponseValidationError, match="outside eligible"):
        validate_pitch_response(request, response)


def test_zero_duration_rest_blocks_exact_shared_boundary() -> None:
    request = PitchRequest(
        notes=(
            PitchNote(0.0, 0.5, 60, "あ", voiced=True),
            PitchNote(0.5, 0.5, 0, "休符", voiced=False),
            PitchNote(0.5, 1.0, 62, "い", voiced=True),
        ),
        request_id="zero-duration-rest",
    )
    response = PitchResponse(
        status="ok",
        pitch_deltas=(PitchDeltaPoint(0.5, 0.25),),
        request_id="zero-duration-rest",
    )
    with pytest.raises(PitchResponseValidationError, match="outside eligible"):
        validate_pitch_response(request, response)


def test_rest_tolerance_blocks_overlapping_voiced_note() -> None:
    request = PitchRequest(
        notes=(
            PitchNote(0.0, 1.0, 60, "あ", voiced=True),
            PitchNote(0.4, 0.6, 0, "休符", voiced=False),
        ),
        request_id="overlap-rest",
    )
    response = PitchResponse(
        status="ok",
        pitch_deltas=(PitchDeltaPoint(0.5, -0.25),),
        request_id="overlap-rest",
    )
    with pytest.raises(PitchResponseValidationError, match="outside eligible"):
        validate_pitch_response(request, response)

