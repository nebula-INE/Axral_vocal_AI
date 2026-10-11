"""Characterize AI pitch units without enabling a Desktop/Web adapter.

These tests deliberately stop at Axral's versioned contract boundary. They are
not proof of Desktop/Web parity and must not be used to change the renderer.
"""
import pytest

from axral_vocal_ai.contracts import (
    PitchDeltaPoint,
    PitchNote,
    PitchRequest,
    PitchResponse,
    request_from_dict,
    response_from_dict,
)
from axral_vocal_ai.pitch_math import (
    midi_note_to_hz,
    semitone_delta_to_frequency_ratio,
)
from axral_vocal_ai.response_validation import (
    PitchResponseValidationError,
    validate_pitch_response,
)


def test_request_round_trip_keeps_seconds_midi_and_rest_metadata() -> None:
    payload = {
        "schema_version": 1,
        "request_id": "desktop-web-audit-1",
        "tempo_bpm": 120.0,
        "notes": [
            {
                "start_sec": 0.125,
                "end_sec": 0.375,
                "midi_note": 60,
                "lyric": "あ",
                "resolved_alias": "- あ",
                "voiced": True,
            },
            {
                "start_sec": 0.375,
                "end_sec": 0.5,
                "midi_note": 0,
                "lyric": "休符",
                "voiced": False,
            },
        ],
    }

    request = request_from_dict(payload)

    assert [(n.start_sec, n.end_sec) for n in request.notes] == [
        (0.125, 0.375),
        (0.375, 0.5),
    ]
    assert [n.midi_note for n in request.notes] == [60, 0]
    assert [n.voiced for n in request.notes] == [True, False]
    assert request.request_id == "desktop-web-audit-1"


@pytest.mark.parametrize(
    ("delta", "expected_ratio"),
    [
        (-2.0, 2.0 ** (-2.0 / 12.0)),
        (-0.125, 2.0 ** (-0.125 / 12.0)),
        (0.0, 1.0),
        (0.125, 2.0 ** (0.125 / 12.0)),
        (2.0, 2.0 ** (2.0 / 12.0)),
    ],
)
def test_signed_semitone_proposals_are_offsets_not_absolute_pitch(
    delta: float, expected_ratio: float
) -> None:
    response = response_from_dict(
        {
            "schema_version": 1,
            "status": "ok",
            "request_id": "signed-offset",
            "pitch_deltas": [
                {"time_sec": 0.25, "delta_semitones": delta},
            ],
        }
    )

    assert response.pitch_deltas[0] == PitchDeltaPoint(0.25, delta)
    assert semitone_delta_to_frequency_ratio(delta) == pytest.approx(expected_ratio)
    # The proposal changes a base frequency by a ratio; it is not itself Hz
    # and must not be treated as an absolute MIDI note or native editor value.
    assert midi_note_to_hz(60.0) * expected_ratio == pytest.approx(
        midi_note_to_hz(60.0 + delta)
    )


def test_proposal_at_shared_voiced_rest_boundary_is_rejected() -> None:
    request = PitchRequest(
        notes=(
            PitchNote(0.0, 0.5, 60, "あ", voiced=True),
            PitchNote(0.5, 0.75, 0, "休符", voiced=False),
        ),
        request_id="rest-boundary",
    )
    response = PitchResponse(
        status="ok",
        pitch_deltas=(PitchDeltaPoint(0.5, -0.25),),
        request_id="rest-boundary",
    )

    with pytest.raises(PitchResponseValidationError, match="outside eligible"):
        validate_pitch_response(request, response)


def test_contract_round_trip_does_not_define_curve_interpolation() -> None:
    response = response_from_dict(
        {
            "schema_version": 1,
            "status": "ok",
            "request_id": "sparse-points",
            "pitch_deltas": [
                {"time_sec": 0.0, "delta_semitones": -1.0},
                {"time_sec": 0.1, "delta_semitones": 1.0},
            ],
        }
    )

    # The contract preserves ordered sparse points and units only. Whether an
    # adapter uses step-hold, linear interpolation, or smoothing is deliberately
    # unspecified until Desktop/Web golden fixtures establish parity.
    assert [(p.time_sec, p.delta_semitones) for p in response.pitch_deltas] == [
        (0.0, -1.0),
        (0.1, 1.0),
    ]
