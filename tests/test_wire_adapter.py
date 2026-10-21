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
    wire_response = deterministic_wire_stub(request)
    assert all("confidence" not in item for item in wire_response["note_results"])
    response = adapt_wire_response(request, wire_response)
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


@pytest.mark.parametrize(
    ("model", "message"),
    [
        (None, "response model must be an object"),
        ({}, "response model.model_id"),
        ({"model_id": "test-model", "model_version": " "}, "response model.model_version"),
    ],
)
def test_wire_adapter_rejects_missing_or_invalid_model_metadata(model, message):
    response = _response()
    response["model"] = model
    with pytest.raises(ValueError, match=message):
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



@pytest.mark.parametrize("bad_status", [[], {}, None, True])
def test_wire_adapter_rejects_non_string_status_values(bad_status):
    response = _response()
    response["status"] = bad_status
    with pytest.raises(ValueError, match="unsupported wire response status"):
        adapt_wire_response(_request(), response)

    response = _response()
    response["note_results"][0]["status"] = bad_status
    with pytest.raises(ValueError, match="unsupported status"):
        adapt_wire_response(_request(), response)


def test_wire_adapter_normalizes_note_result_order_to_absolute_time_order():
    request = _request()
    response = _response()
    response["note_results"].reverse()

    adapted = adapt_wire_response(request, response)
    assert [(point.time_sec, point.delta_semitones) for point in adapted.pitch_deltas] == [
        (0.1, 0.5), (0.3, -0.25), (0.7, 1.0)
    ]



@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda request: request["voicebank"].update(alias_resolution_status="ambiguous"),
         "alias resolution must be resolved"),
        (lambda request: request["controls"].update(strength=1.1),
         "strength must be in"),
        (lambda request: request["notes"][0].update(sample_ref="/private/voice.wav"),
         "sample_ref must not be an absolute path"),
        (lambda request: request["notes"][0].update(resolved_alias=""),
         "resolved_alias"),
        (lambda request: request["notes"][0].update(
            baseline_pitch=[{"time_ms": 100.0, "hz": 440.0},
                            {"time_ms": 50.0, "hz": 442.0}]),
         "baseline_pitch must be time-ordered"),
        (lambda request: request["controls"].update(enabled_features=["pitch_delta", "pitch_delta"]),
         "duplicate or unsupported features"),
    ],
)
def test_wire_adapter_rejects_unsafe_request_metadata(mutate, message):
    request = _request()
    mutate(request)
    with pytest.raises(ValueError, match=message):
        adapt_wire_response(request, _response())


@pytest.mark.parametrize("sample_ref", [
    "https://example.invalid/voice.wav",
    "file:///tmp/voice.wav",
    "voicebank://another-profile/a.wav",
    "voicebank://local-profile/%2e%2e/outside.wav",
    "voicebank://local-profile/a.wav?download=1",
    "voicebank://local-profile/a.wav#fragment",
])
def test_wire_adapter_rejects_nonlocal_or_mismatched_sample_uris(sample_ref):
    request = _request()
    request["notes"][0]["sample_ref"] = sample_ref
    with pytest.raises(ValueError):
        deterministic_wire_stub(request)


def test_wire_adapter_accepts_voicebank_uri_for_matching_profile():
    request = _request()
    request["notes"][0]["sample_ref"] = "voicebank://local-profile/subdir/a.wav"
    assert deterministic_wire_stub(request)["status"] == "ok"


def test_wire_stub_validates_request_metadata_before_returning_noop():
    request = _request()
    request["notes"][0]["sample_ref"] = "C:\\voicebank\\a.wav"
    with pytest.raises(ValueError, match="absolute path"):
        deterministic_wire_stub(request)



def test_wire_adapter_rejects_integer_too_large_for_float_conversion():
    request = _request()
    request["notes"][0]["start_ms"] = 10**400
    with pytest.raises(ValueError, match="finite number"):
        deterministic_wire_stub(request)

    response = _response()
    response["note_results"][0]["pitch_delta"][0]["delta_cents"] = 10**400
    with pytest.raises(ValueError, match="finite number"):
        adapt_wire_response(_request(), response)



@pytest.mark.parametrize("sample_ref", [
    "../outside.wav",
    "voicebank://local-profile/../outside.wav",
    r"voicebank://local-profile\..\outside.wav",
])
def test_wire_adapter_rejects_sample_ref_path_traversal(sample_ref):
    request = _request()
    request["notes"][0]["sample_ref"] = sample_ref
    with pytest.raises(ValueError, match="path traversal"):
        deterministic_wire_stub(request)


def test_wire_adapter_accepts_no_change_for_individual_note():
    request = _request()
    response = _response()
    response["note_results"][0]["status"] = "no_change"
    response["note_results"][0]["pitch_delta"] = []
    adapted = adapt_wire_response(request, response)
    assert adapted.status == "ok"
    assert [(point.time_sec, point.delta_semitones) for point in adapted.pitch_deltas] == [
        (0.7, 1.0)
    ]


def test_wire_adapter_rejects_pitch_deltas_on_no_change_note():
    response = _response()
    response["note_results"][0]["status"] = "no_change"
    with pytest.raises(ValueError, match="no_change status cannot contain pitch deltas"):
        adapt_wire_response(_request(), response)

def test_wire_adapter_accepts_missing_optional_confidence():
    response = _response()
    for note_result in response["note_results"]:
        note_result.pop("confidence")
    adapted = adapt_wire_response(_request(), response)
    assert adapted.status == "ok"
    assert [(point.time_sec, point.delta_semitones) for point in adapted.pitch_deltas] == [
        (0.1, 0.5), (0.3, -0.25), (0.7, 1.0)
    ]

