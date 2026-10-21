from __future__ import annotations

import struct
from pathlib import Path

import pytest

from axral_vocal_ai.voicebank_analysis import analyze_voicebank
from axral_vocal_ai.wire_request_builder import WireRequestBuildError, build_wire_request


def _write_wav(path: Path) -> None:
    sample_rate = 8000
    frames = 80
    fmt = struct.pack("<HHIIHH", 1, 1, sample_rate, sample_rate * 2, 2, 16)
    data = bytes(frames * 2)
    chunks = b"fmt " + struct.pack("<I", len(fmt)) + fmt
    chunks += b"data" + struct.pack("<I", len(data)) + data
    path.write_bytes(b"RIFF" + struct.pack("<I", len(chunks) + 4) + b"WAVE" + chunks)


def test_duplicate_alias_across_nested_oto_files_is_not_guessed(tmp_path: Path) -> None:
    (tmp_path / "oto.ini").write_text(
        "a.wav=あ,0,100,-100,20,10\n", encoding="utf-8"
    )
    nested = tmp_path / "append"
    nested.mkdir()
    (nested / "oto.ini").write_text(
        "b.wav=あ,0,100,-100,20,10\n", encoding="utf-8"
    )
    _write_wav(tmp_path / "a.wav")
    _write_wav(nested / "b.wav")

    analysis = analyze_voicebank(tmp_path)
    assert analysis.summary["oto_files"] == 2
    assert analysis.summary["duplicate_alias_groups"] == 1

    with pytest.raises(WireRequestBuildError, match="alias resolution is ambiguous") as exc:
        build_wire_request(
            analysis,
            [{
                "note_id": "note-1",
                "midi_note": 60,
                "start_ms": 0,
                "duration_ms": 250,
                "alias": "あ",
            }],
            profile_id="test-bank",
            profile_version="1",
            request_id="nested-duplicate-alias",
        )

    assert exc.value.status == "needs_review"
