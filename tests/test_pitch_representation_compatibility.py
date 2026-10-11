"""Characterize AI pitch units without enabling a Desktop/Web adapter.

These tests deliberately stop at Axral's versioned contract boundary. They are
not proof of Desktop/Web parity and must not be used to change the renderer.
"""
import json
from pathlib import Path

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



_FIXTURES = Path(__file__).parent / "fixtures"


def _read_fixture(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def test_current_desktop_gui_fixture_uses_parameters_pitch_shape() -> None:
    """Pin the current GUI JSON shape without assigning units to raw values."""
    payload = _read_fixture("desktop_gui_project_pitch.json")

    assert set(payload["parameters"]) == {"Pitch", "Gender", "Tension", "Breath"}
    assert "pitch_automation" not in payload
    assert payload["tracks"][0]["notes"]
    assert payload["parameters"]["Pitch"] == [
        {"time": 0.0, "value": 0},
        {"time": 0.125, "value": 2048},
        {"time": 0.25, "value": -4096},
    ]
    # The raw value is intentionally preserved: this fixture test does not
    # reinterpret Desktop automation integers as semitone offsets.
    assert [point["value"] for point in payload["parameters"]["Pitch"]] == [
        0, 2048, -4096
    ]


def test_legacy_model_fixture_uses_distinct_pitch_automation_shape() -> None:
    """Keep the legacy model representation distinct from current GUI JSON."""
    payload = _read_fixture("legacy_project_model_pitch.json")

    assert set(payload) == {"pitch_automation"}
    assert payload["pitch_automation"] == [
        {"time": 0.0, "value": 0.0},
        {"time": 0.125, "value": 0.5},
        {"time": 0.25, "value": -1.0},
    ]
    assert "parameters" not in payload


def test_desktop_pitch_fixtures_are_not_silently_interchangeable() -> None:
    gui_payload = _read_fixture("desktop_gui_project_pitch.json")
    legacy_payload = _read_fixture("legacy_project_model_pitch.json")

    # A consumer must choose an explicit format-specific adapter. Similar
    # {time, value} point objects do not make the document envelopes equivalent.
    assert "parameters" in gui_payload and "pitch_automation" not in gui_payload
    assert "pitch_automation" in legacy_payload and "parameters" not in legacy_payload
    assert gui_payload["parameters"]["Pitch"] != legacy_payload["pitch_automation"]
