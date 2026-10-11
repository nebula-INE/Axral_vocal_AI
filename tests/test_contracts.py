import pytest

from axral_vocal_ai.contracts import (
    PitchDeltaPoint,
    PitchNote,
    PitchRequest,
    PitchResponse,
    request_from_dict,
    response_from_dict,
)


def test_valid_request_preserves_original_alias_and_unresolved_alias() -> None:
    request = PitchRequest(
        notes=[
            PitchNote(0.0, 0.4, 60, "あ", resolved_alias="- あ", voiced=True),
            PitchNote(0.4, 0.8, 62, "い", resolved_alias=None, voiced=None),
        ],
        request_id="test-1",
    )
    assert request.notes[0].resolved_alias == "- あ"
    assert request.notes[1].resolved_alias is None
    assert request.schema_version == 1


def test_note_rejects_invalid_time_and_midi() -> None:
    with pytest.raises(ValueError):
        PitchNote(1.0, 0.0, 60, "あ")
    with pytest.raises(ValueError):
        PitchNote(0.0, 1.0, 128, "あ")


def test_request_rejects_out_of_order_notes() -> None:
    with pytest.raises(ValueError, match="ordered"):
        PitchRequest(
            notes=[
                PitchNote(1.0, 1.2, 60, "あ"),
                PitchNote(0.5, 0.8, 62, "い"),
            ]
        )


def test_request_rejects_unknown_schema_version() -> None:
    with pytest.raises(ValueError, match="schema_version"):
        PitchRequest(notes=[], schema_version=99)


def test_response_requires_ordered_finite_points() -> None:
    with pytest.raises(ValueError, match="ordered"):
        PitchResponse(
            status="ok",
            pitch_deltas=[
                PitchDeltaPoint(1.0, 0.1),
                PitchDeltaPoint(0.5, 0.2),
            ],
        )
    with pytest.raises(ValueError, match="finite"):
        PitchDeltaPoint(float("nan"), 0.0)


def test_non_ok_response_cannot_contain_pitch_changes() -> None:
    with pytest.raises(ValueError, match="only an 'ok'"):
        PitchResponse(
            status="no_change",
            pitch_deltas=[PitchDeltaPoint(0.0, 0.0)],
        )


def test_dict_parsers_validate_external_payloads() -> None:
    request = request_from_dict({
        "schema_version": 1,
        "notes": [{"start_sec": 0, "end_sec": 1, "midi_note": 60, "lyric": "あ"}],
    })
    assert len(request.notes) == 1

    response = response_from_dict({
        "schema_version": 1,
        "status": "ok",
        "pitch_deltas": [{"time_sec": 0.0, "delta_semitones": 0.25}],
    })
    assert response.pitch_deltas[0].delta_semitones == 0.25


def test_dict_parser_rejects_unknown_version() -> None:
    with pytest.raises(ValueError, match="schema_version"):
        request_from_dict({"schema_version": 2, "notes": []})



def test_response_parser_preserves_seconds_and_signed_semitone_deltas() -> None:
    # These values are AI-contract units only: seconds + relative semitones.
    # They must not be interpreted as UST PBS tenths, native automation values,
    # MIDI note numbers, or absolute Hz values.
    response = response_from_dict(
        {
            "schema_version": 1,
            "status": "ok",
            "request_id": "pitch-units-1",
            "pitch_deltas": [
                {"time_sec": 0.125, "delta_semitones": -1.5},
                {"time_sec": 0.375, "delta_semitones": 0.75},
            ],
        }
    )

    assert response.request_id == "pitch-units-1"
    assert [(point.time_sec, point.delta_semitones) for point in response.pitch_deltas] == [
        (0.125, -1.5),
        (0.375, 0.75),
    ]


def test_response_parser_rejects_non_finite_pitch_values() -> None:
    with pytest.raises(ValueError, match="finite"):
        response_from_dict(
            {
                "schema_version": 1,
                "status": "ok",
                "pitch_deltas": [
                    {"time_sec": 0.25, "delta_semitones": float("nan")}
                ],
            }
        )


def test_response_parser_rejects_unsorted_pitch_points() -> None:
    with pytest.raises(ValueError, match="ordered"):
        response_from_dict(
            {
                "schema_version": 1,
                "status": "ok",
                "pitch_deltas": [
                    {"time_sec": 0.5, "delta_semitones": 0.25},
                    {"time_sec": 0.25, "delta_semitones": -0.25},
                ],
            }
        )


def test_response_parser_rejects_non_list_pitch_deltas() -> None:
    with pytest.raises(ValueError, match="pitch_deltas must be a list"):
        response_from_dict({"status": "ok", "pitch_deltas": {"time_sec": 0.0}})


def test_response_parser_rejects_non_object_pitch_delta_entries() -> None:
    with pytest.raises(ValueError, match="entries must be objects"):
        response_from_dict({"status": "ok", "pitch_deltas": [0.25]})
