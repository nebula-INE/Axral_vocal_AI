from __future__ import annotations

import struct
from pathlib import Path

from axral_vocal_ai.voicebank_analysis import analyze_voicebank
from axral_vocal_ai.wire_adapter import adapt_wire_response, deterministic_wire_stub
from axral_vocal_ai.wire_request_builder import build_wire_request


def _write_wav(path: Path) -> None:
    """Write a minimal valid PCM WAV fixture; no audio processing is exercised."""
    sample_rate = 8000
    frames = 80
    fmt = struct.pack("<HHIIHH", 1, 1, sample_rate, sample_rate * 2, 2, 16)
    data = bytes(frames * 2)
    chunks = b"fmt " + struct.pack("<I", len(fmt)) + fmt
    chunks += b"data" + struct.pack("<I", len(data)) + data
    path.write_bytes(b"RIFF" + struct.pack("<I", len(chunks) + 4) + b"WAVE" + chunks)


def test_voicebank_audit_to_wire_stub_is_traceable_and_non_destructive(tmp_path: Path) -> None:
    (tmp_path / "oto.ini").write_text(
        "a.wav=あ,0,100,-100,20,10\n", encoding="utf-8"
    )
    (tmp_path / "prefix.map").write_text("C1\t-\t-\n", encoding="utf-8")
    _write_wav(tmp_path / "a.wav")
    notes = [{
        "note_id": "note-1",
        "midi_note": 60,
        "start_ms": 0,
        "duration_ms": 250,
        "alias": "あ",
        "lyric": "あ",
    }]
    original_notes = [dict(note) for note in notes]

    analysis = analyze_voicebank(tmp_path)
    request = build_wire_request(
        analysis,
        notes,
        profile_id="test-bank",
        profile_version="1",
        request_id="integration-1",
    )
    response = deterministic_wire_stub(request)
    adapted = adapt_wire_response(request, response)

    assert analysis.summary["oto_entries"] == 1
    assert request["notes"][0]["resolved_alias"] == "あ"
    assert request["notes"][0]["sample_ref"] == "voicebank://test-bank/a.wav"
    assert str(tmp_path) not in request["notes"][0]["sample_ref"]
    assert response["model"]["model_id"] == "deterministic-no-op-stub"
    assert adapted.status == "no_change"
    assert adapted.pitch_deltas == ()
    assert notes == original_notes



def test_voicebank_pipeline_preserves_baseline_pitch_and_adapts_note_relative_proposal(
    tmp_path: Path,
) -> None:
    (tmp_path / "oto.ini").write_text(
        "a.wav=あ,0,100,-100,20,10\n", encoding="utf-8"
    )
    _write_wav(tmp_path / "a.wav")
    notes = [{
        "note_id": "note-pitch",
        "midi_note": 60,
        "start_ms": 125,
        "duration_ms": 250,
        "alias": "あ",
        "lyric": "あ",
        "baseline_pitch": [
            {"time_ms": 0, "hz": 261.6256},
            {"time_ms": 250, "hz": 261.6256},
        ],
    }]
    original_notes = [dict(note) for note in notes]
    analysis = analyze_voicebank(tmp_path)
    request = build_wire_request(
        analysis, notes, profile_id="test-bank", profile_version="1",
        request_id="baseline-pitch-integration",
    )

    assert request["notes"][0]["baseline_pitch"] == [
        {"time_ms": 0.0, "hz": 261.6256},
        {"time_ms": 250.0, "hz": 261.6256},
    ]

    response = {
        "contract": "axral.vocal-expression.response",
        "schema_version": "1.0",
        "request_id": "baseline-pitch-integration",
        "status": "ok",
        "model": {"model_id": "fixture-model", "model_version": "test"},
        "note_results": [{
            "note_id": "note-pitch",
            "status": "ok",
            "pitch_delta": [
                {"time_ms": 50, "delta_cents": 25},
                {"time_ms": 200, "delta_cents": -50},
            ],
            "warnings": [],
        }],
        "warnings": [],
    }
    adapted = adapt_wire_response(request, response)

    assert [(point.time_sec, point.delta_semitones) for point in adapted.pitch_deltas] == [
        (0.175, 0.25),
        (0.325, -0.5),
    ]
    assert notes == original_notes
