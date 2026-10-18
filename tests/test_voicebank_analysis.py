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
    assert all(item.signal is not None for item in result.wav_files)
    assert all("digital_silence" in item.signal.issues for item in result.wav_files)
    assert len(result.prefix_entries) == 1
    report = json.loads(result.to_json())
    assert report["schema_version"] == 1
    assert "signal" in report["wav_files"][0]


def test_resolves_wav_path_case_insensitively_like_vo_se(tmp_path: Path) -> None:
    actual_dir = tmp_path / "SubVoice"
    actual_dir.mkdir()
    write_silent_wav(actual_dir / "Audio.WAV")
    (tmp_path / "oto.ini").write_text(
        "subvoice/audio.wav=あ,0,100,-100,20,10\n", encoding="utf-8"
    )

    result = analyze_voicebank(tmp_path)

    assert result.entries[0].wav_filename == "SubVoice/Audio.WAV"
    assert result.summary["wav_files_checked"] == 1
    assert not any(issue.code == "wav_missing" for issue in result.issues)


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



def test_deduplicates_wav_audits_and_summarizes_signal_findings(tmp_path: Path) -> None:
    # Two aliases can reference the same sample; audit the file once, not once per alias.
    (tmp_path / "oto.ini").write_text(
        "same.wav=あ,0,100,-100,20,10\nsame.wav=い,0,100,-100,20,10\n",
        encoding="utf-8",
    )
    write_silent_wav(tmp_path / "same.wav", frames=32)

    result = analyze_voicebank(tmp_path)

    assert result.summary["oto_entries"] == 2
    assert result.summary["wav_files_checked"] == 1
    assert result.summary["wav_files_with_signal_issues"] == 1
    assert result.summary["wav_files_digital_silence"] == 1
    assert result.summary["wav_files_near_silence"] == 0
    assert result.summary["wav_files_clipping_suspected"] == 0
    report = json.loads(result.to_json())
    assert report["summary"]["wav_files_digital_silence"] == 1
    assert report["wav_files"][0]["signal"]["issues"] == ["digital_silence"]

def test_summary_counts_truncated_riff_as_invalid_wav(tmp_path: Path) -> None:
    path = tmp_path / "truncated.wav"
    write_silent_wav(path)
    raw = bytearray(path.read_bytes())
    struct.pack_into("<I", raw, 4, len(raw) + 100)
    path.write_bytes(raw)
    (tmp_path / "oto.ini").write_text(
        "truncated.wav=あ,0,100,-100,20,10\n", encoding="utf-8"
    )

    result = analyze_voicebank(tmp_path)

    assert result.summary["wav_files_checked"] == 1
    assert result.summary["wav_files_invalid"] == 1
    assert any(issue.code == "wav_riff_size_exceeds_file" for issue in result.issues)


def test_reports_malformed_existing_wav(tmp_path: Path) -> None:
    (tmp_path / "broken.wav").write_bytes(b"RIFF")
    (tmp_path / "oto.ini").write_text(
        "broken.wav=あ,0,100,-100,20,10\n", encoding="utf-8"
    )

    result = analyze_voicebank(tmp_path)

    assert result.summary["wav_files_checked"] == 1
    assert result.summary["wav_files_invalid"] == 1
    assert any(issue.code == "wav_invalid" for issue in result.issues)
    report = json.loads(result.to_json())
    assert report["wav_files"][0]["path"] == "broken.wav"
    assert report["wav_files"][0]["metadata"] is None
    assert report["wav_files"][0]["error"]


def test_utf8_voicebank_metadata_is_not_misread_as_cp932(tmp_path: Path) -> None:
    """Valid UTF-8 should win over CP932 when both decoders accept the bytes."""
    (tmp_path / "oto.ini").write_text(
        "hello.wav=こんにちは,0,100,-100,20,10\n", encoding="utf-8"
    )
    write_silent_wav(tmp_path / "hello.wav")

    result = analyze_voicebank(tmp_path)

    assert result.entries[0].alias == "こんにちは"
    assert not any(issue.code == "oto_parse_issue" for issue in result.issues)
