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
