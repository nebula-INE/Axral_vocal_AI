from __future__ import annotations

import json
from pathlib import Path

from axral_vocal_ai.voicebank_analysis import analyze_voicebank


def test_scans_nested_oto_and_rebases_wav_paths(tmp_path: Path) -> None:
    (tmp_path / "oto.ini").write_text("a.wav=あ,0,100,-100,20,10\n", encoding="utf-8")
    (tmp_path / "a.wav").write_bytes(b"RIFF")
    nested = tmp_path / "voice"
    nested.mkdir()
    (nested / "oto.ini").write_text("sub\\i.wav=い,0,100,-100,20,10\n", encoding="utf-8")
    (nested / "sub").mkdir()
    (nested / "sub" / "i.wav").write_bytes(b"RIFF")
    (tmp_path / "prefix.map").write_text("C4\t-\t_C4\n", encoding="utf-8")

    result = analyze_voicebank(tmp_path)

    assert result.summary["oto_files"] == 2
    assert result.summary["oto_entries"] == 2
    assert {entry.wav_filename for entry in result.entries} == {"a.wav", "voice/sub/i.wav"}
    assert result.summary["errors"] == 0
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
    (tmp_path / "a.wav").write_bytes(b"RIFF")
    result = analyze_voicebank(tmp_path)
    assert result.entries[0].alias == "あ"
