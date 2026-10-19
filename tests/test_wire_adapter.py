import copy

import pytest

from axral_vocal_ai.response_validation import PitchResponseValidationError
from axral_vocal_ai.wire_adapter import adapt_wire_response, deterministic_wire_stub


def _request():
    return {
        "contract": "axral.vocal-expression.request",
        "schema_version": "1.0",
        "request_id": "wire-1",
        "voicebank": {"profile_id": "local-profile", "profile_version": "1",
                      "alias_resolution_status": "resolved"},
        "notes": [
            {"note_id": "n1", "midi_note": 60, "start_ms": 0.0,
             "duration_ms": 500.0, "lyric": "あ", "resolved_alias": "あ",
             "sample_ref": "local-ref-1", "voiced": True},
            {"note_id": "n2", "midi_note": 62, "start_ms": 500.0,
             "duration_ms": 400.0, "lyric": "い", "resolved_alias": "い",
             "sample_ref": "local-ref-2", "voiced": True},
        ],
        "controls": {"enabled_features": ["pitch_delta"], "strength": 1.0},
    }


def _response():
    return {
        "contract": "axral.vocal-expression.response",
        "schema_version": "1.0",
        "request_id": "wire-1",
        "status": "ok",
        "model": {"model_id": "test-model", "model_version": "1"},
        "note_results": [
            {"note_id": "n1", "status": "ok", "pitch_delta": [
                {"time_ms": 100.0, "delta_cents": 50.0},
                {"time_ms": 300.0, "delta_cents": -25.0},
            ], "confidence": 0.9, "warnings": []},
            {"note_id": "n2", "status": "ok", "pitch_delta": [
                {"time_ms": 200.0, "delta_cents": 100.0},
            ], "confidence": 0.8, "warnings": []},
        ],
        "warnings": [],
    }


def test_wire_adapter_converts_relative_ms_and_cents_to_absolute_seconds_and_semitones():
    response = adapt_wire_response(_request(), _response())
    assert response.status == "ok"
    assert [(p.time_sec, p.delta_semitones) for p in response.pitch_deltas] == [
        (0.1, 0.5), (0.3, -0.25), (0.7, 1.0)
    ]


def test_wire_adapter_no_op_stub_produces_internal_no_change():
    request = _request()
    response = adapt_wire_response(request, deterministic_wire_stub(request))
    assert response.status == "no_change"
    assert response.pitch_deltas == ()


@pytest.mark.parametrize("bad_version", ["2.0", 1, True, None])
def test_wire_adapter_rejects_unsupported_versions(bad_version):
    response = _response()
    response["schema_version"] = bad_version
    with pytest.raises(ValueError, match="schema_version"):
        adapt_wire_response(_request(), response)


def test_wire_adapter_rejects_mismatched_request_id():
    response = _response()
    response["request_id"] = "other"
    with pytest.raises(ValueError, match="request_id"):
        adapt_wire_response(_request(), response)


def test_wire_adapter_rejects_duplicate_and_unknown_note_ids():
    response = _response()
    response["note_results"][1]["note_id"] = "n1"
    with pytest.raises(ValueError, match="duplicate"):
        adapt_wire_response(_request(), response)

    response = _response()
    response["note_results"][1]["note_id"] = "unknown"
    with pytest.raises(ValueError, match="unknown"):
        adapt_wire_response(_request(), response)


def test_wire_adapter_rejects_missing_note_result_and_partial_status():
    response = _response()
    response["note_results"].pop()
    with pytest.raises(ValueError, match="missing note results"):
        adapt_wire_response(_request(), response)

    response = _response()
    response["status"] = "partial"
    with pytest.raises(ValueError, match="requires review"):
        adapt_wire_response(_request(), response)


def test_wire_adapter_rejects_invalid_confidence_and_non_finite_delta():
    response = _response()
    response["note_results"][0]["confidence"] = 1.1
    with pytest.raises(ValueError, match="confidence"):
        adapt_wire_response(_request(), response)

    response = _response()
    response["note_results"][0]["pitch_delta"][0]["delta_cents"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        adapt_wire_response(_request(), response)


def test_wire_adapter_rejects_out_of_note_range_and_unsafe_delta():
    response = _response()
    response["note_results"][0]["pitch_delta"][0]["time_ms"] = 600.0
    with pytest.raises(ValueError, match="outside note duration"):
        adapt_wire_response(_request(), response)

    response = _response()
    response["note_results"][0]["pitch_delta"][0]["delta_cents"] = 250.0
    with pytest.raises(PitchResponseValidationError, match="safety bound"):
        adapt_wire_response(_request(), response)


def test_wire_adapter_rejects_duplicate_request_ids_and_does_not_mutate_inputs():
    request = _request()
    request["notes"][1]["note_id"] = "n1"
    with pytest.raises(ValueError, match="duplicate note_id"):
        deterministic_wire_stub(request)

    request = _request()
    original_request = copy.deepcopy(request)
    response = _response()
    original_response = copy.deepcopy(response)
    adapt_wire_response(request, response)
    assert request == original_request
    assert response == original_response
