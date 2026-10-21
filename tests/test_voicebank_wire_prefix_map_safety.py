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


@pytest.mark.parametrize(
    ("root_map", "nested_map"),
    [
        ("C4\t-\t_ROOT\n", "C4\t-\t_NESTED\n"),
        ("C4\t-\t_ROOT\n", "F4\t-\t_NESTED\n"),
    ],
    ids=("same-boundary", "different-boundary"),
)
def test_nested_prefix_maps_fail_closed_before_wire_request(
    tmp_path: Path, root_map: str, nested_map: str
) -> None:
    (tmp_path / "oto.ini").write_text(
        "a.wav=あ,0,100,-100,20,10\n", encoding="utf-8"
    )
    _write_wav(tmp_path / "a.wav")
    (tmp_path / "prefix.map").write_text(root_map, encoding="utf-8")
    nested = tmp_path / "voice"
    nested.mkdir()
    (nested / "prefix.map").write_text(nested_map, encoding="utf-8")

    analysis = analyze_voicebank(tmp_path)
    assert "nested_prefix_map" in {issue.code for issue in analysis.issues}

    with pytest.raises(WireRequestBuildError, match="multiple/nested prefix.map") as exc:
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
            request_id="nested-prefix-map",
        )

    assert exc.value.status == "needs_review"
