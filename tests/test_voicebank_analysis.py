from __future__ import annotations

import json
import struct
from pathlib import Path

from axral_vocal_ai.voicebank_analysis import analyze_voicebank


def write_silent_wav(path: Path, *, sample_rate: int = 44100, frames: int = 441) -> None:
    fmt = struct.pack("<HHIIHH", 1, 1, sample_rate, sample_rate * 2, 2, 16)
    data = bytes(frames * 2)
    chunks = b"fmt " + struct.pack("<I", len(fmt)) + fmt
    chunks += b"data" + struct.pack("<I", len(data)) + data
    path.write_bytes(b"RIFF" + struct.pack("<I", len(chunks) + 4) + b"WAVE" + chunks)


def test_scans_nested_oto_and_rebases_wav_paths(tmp_path: Path) -> None:
    (tmp_path / "oto.ini").write_text("a.wav=あ,0,100,-100,20,10\n", encoding="utf-8")
    write_silent_wav(tmp_path / "a.wav")
    nested = tmp_path / "voice"
    nested.mkdir()
    (nested / "oto.ini").write_text("sub\\i.wav=い,0,100,-100,20,10\n", encoding="utf-8")
    (nested / "sub").mkdir()
    write_silent_wav(nested / "sub" / "i.wav")
    (tmp_path / "prefix.map").write_text("C4\t-\t_C4\n", encoding="utf-8")

    result = analyze_voicebank(tmp_path)

    assert result.summary["oto_files"] == 2
    assert result.summary["oto_entries"] == 2
    assert {entry.wav_filename for entry in result.entries} == {"a.wav", "voice/sub/i.wav"}
    assert result.summary["errors"] == 0
    assert result.summary["wav_files_checked"] == 2
    assert result.summary["wav_files_invalid"] == 0
    assert {item.path for item in result.wav_files} == {"a.wav", "voice/sub/i.wav"}
    assert len(result.prefix_entries) == 1
    assert json.loads(result.to_json())["schema_version"] == 1


def test_reports_missing_wav_and_duplicate_alias(tmp_path: Path) -> None:
    (tmp_path / "oto.ini").write_text(
        "missing.wav=あ,0,100,-100,20,10\nother.wav=あ,0,100,-100,20,10\n",
        encoding="utf-8",
    )
    result = analyze_voicebank(tmp_path)
    codes = [issue.code for issue in result.issues]
    assert codes.count("wav_missing") == 2
    assert "duplicate_alias" in codes
    assert result.summary["duplicate_alias_groups"] == 1


def test_reports_path_escape_and_bad_oto_line(tmp_path: Path) -> None:
    (tmp_path / "oto.ini").write_text(
        "../outside.wav=あ,0,100,-100,20,10\nmalformed line\n",
        encoding="utf-8",
    )
    result = analyze_voicebank(tmp_path)
    codes = [issue.code for issue in result.issues]
    assert "wav_path_escape" in codes
    assert "oto_parse_issue" in codes


def test_missing_inventory_is_actionable(tmp_path: Path) -> None:
    result = analyze_voicebank(tmp_path)
    codes = {issue.code for issue in result.issues}
    assert {"oto_not_found", "no_oto_entries", "prefix_map_not_found"} <= codes


def test_cp932_voicebank_metadata_is_supported(tmp_path: Path) -> None:
    (tmp_path / "oto.ini").write_bytes("a.wav=あ,0,100,-100,20,10\n".encode("cp932"))
    write_silent_wav(tmp_path / "a.wav")
    result = analyze_voicebank(tmp_path)
    assert result.entries[0].alias == "あ"


def test_reports_malformed_existing_wav(tmp_path: Path) -> None:
    (tmp_path / "broken.wav").write_bytes(b"RIFF")
    (tmp_path / "oto.ini").write_text(
        "broken.wav=あ,0,100,-100,20,10\\n", encoding="utf-8"
    )

    result = analyze_voicebank(tmp_path)

    assert result.summary["wav_files_checked"] == 1
    assert result.summary["wav_files_invalid"] == 1
    assert any(issue.code == "wav_invalid" for issue in result.issues)
    report = json.loads(result.to_json())
    assert report["wav_files"][0]["path"] == "broken.wav"
    assert report["wav_files"][0]["metadata"] is None
    assert report["wav_files"][0]["error"]
