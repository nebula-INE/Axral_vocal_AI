from __future__ import annotations

import json
from pathlib import Path
import struct
import wave

import pytest

from axral_vocal_ai.voicebank_analysis import analyze_voicebank
from axral_vocal_ai.voicebank_alias import resolve_utau_alias


def write_pcm_wav(path: Path, samples: list[int], *, sample_rate: int = 44100) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(struct.pack("<" + "h" * len(samples), *samples))


def test_voicebank_scan_to_pitch_aware_alias_resolution_and_json_report(
    tmp_path: Path,
) -> None:
    """Exercise the real filesystem pipeline, not isolated parser components."""
    root = tmp_path / "voicebank"
    nested = root / "voice"
    nested.mkdir(parents=True)

    # The nested oto.ini WAV path is relative to that oto.ini, then rebased
    # by the scanner to the voicebank root for downstream resolution.
    write_pcm_wav(nested / "a.wav", [1000, -1000, 2000, -2000] * 128)
    (nested / "oto.ini").write_text(
        "a.wav=あ_F4,0,100,-100,20,10\n", encoding="utf-8"
    )
    (root / "prefix.map").write_text("C1\t\t_C4\nF4\t\t_F4\n", encoding="utf-8")

    analysis = analyze_voicebank(root)

    assert analysis.summary["oto_files"] == 1
    assert analysis.summary["oto_entries"] == 1
    assert analysis.summary["wav_files_checked"] == 1
    assert analysis.summary["wav_files_invalid"] == 0
    assert analysis.summary["errors"] == 0
    assert analysis.entries[0].wav_filename == "voice/a.wav"
    assert analysis.wav_files[0].metadata is not None
    assert analysis.wav_files[0].signal is not None
    assert "digital_silence" not in analysis.wav_files[0].signal.issues

    resolved = resolve_utau_alias(
        "あ", 65, analysis.entries, analysis.prefix_entries, voicebank_root=root
    )
    assert resolved.status == "resolved"
    assert resolved.mapped_alias == "あ_F4"
    assert len(resolved.candidates) == 1
    assert resolved.candidates[0].wav_path == (root / "voice/a.wav").resolve()

    # The report is stable JSON-ready audit output and keeps paths relative.
    report = json.loads(analysis.to_json())
    assert report["schema_version"] == 1
    assert report["entries"][0]["wav_filename"] == "voice/a.wav"
    assert report["wav_files"][0]["path"] == "voice/a.wav"
    assert report["wav_files"][0]["signal"]["status"] == "ok"


def test_end_to_end_pipeline_does_not_resolve_duplicate_alias_silently(
    tmp_path: Path,
) -> None:
    root = tmp_path / "voicebank"
    root.mkdir()
    write_pcm_wav(root / "first.wav", [1000, -1000] * 64)
    write_pcm_wav(root / "second.wav", [2000, -2000] * 64)
    (root / "oto.ini").write_text(
        "first.wav=あ,0,100,-100,20,10\n"
        "second.wav=あ,0,100,-100,20,10\n",
        encoding="utf-8",
    )

    analysis = analyze_voicebank(root)
    resolved = resolve_utau_alias("あ", 60, analysis.entries, voicebank_root=root)

    assert analysis.summary["duplicate_alias_groups"] == 1
    assert resolved.status == "ambiguous"
    assert len(resolved.candidates) == 2
    assert any("no candidate was selected" in issue for issue in resolved.issues)



def test_absolute_wav_path_is_rejected_by_end_to_end_audit(tmp_path: Path) -> None:
    root = tmp_path / "voicebank"
    root.mkdir()
    outside = tmp_path / "outside.wav"
    write_pcm_wav(outside, [1000, -1000] * 64)
    (root / "oto.ini").write_text(
        f"{outside}=あ,0,100,-100,20,10\n", encoding="utf-8"
    )

    analysis = analyze_voicebank(root)

    assert any(issue.code == "absolute_wav_path" for issue in analysis.issues)
    assert analysis.summary["errors"] >= 1
    # Absolute paths are never accepted as an in-bank relative sample path.
    assert analysis.entries[0].wav_filename == str(outside)

def test_windows_drive_wav_path_is_rejected_on_any_host(tmp_path: Path) -> None:
    """Windows absolute paths must not become valid relative paths on POSIX."""
    root = tmp_path / "voicebank"
    root.mkdir()
    (root / "oto.ini").write_text(
        "C:\\outside\\voice.wav=あ,0,100,-100,20,10" + chr(10), encoding="utf-8"
    )

    analysis = analyze_voicebank(root)

    assert any(issue.code == "absolute_wav_path" for issue in analysis.issues)
    assert analysis.summary["errors"] >= 1
    assert analysis.entries[0].wav_filename.replace(chr(92), "/") == "C:/outside/voice.wav"


def test_invalid_wav_is_reported_without_aborting_other_samples(tmp_path: Path) -> None:
    root = tmp_path / "voicebank"
    root.mkdir()
    write_pcm_wav(root / "valid.wav", [1000, -1000] * 64)
    (root / "broken.wav").write_bytes(b"not a RIFF/WAVE file")
    (root / "oto.ini").write_text(
        "valid.wav=あ,0,100,-100,20,10\n"
        "broken.wav=い,0,100,-100,20,10\n",
        encoding="utf-8",
    )

    analysis = analyze_voicebank(root)

    assert analysis.summary["oto_entries"] == 2
    assert analysis.summary["wav_files_checked"] == 2
    assert analysis.summary["wav_files_invalid"] == 1
    assert any(issue.code == "wav_invalid" for issue in analysis.issues)
    audits_by_path = {item.path: item for item in analysis.wav_files}
    assert audits_by_path["broken.wav"].metadata is None
    assert audits_by_path["broken.wav"].error is not None
    assert audits_by_path["valid.wav"].metadata is not None
    assert audits_by_path["valid.wav"].signal is not None

def test_parent_directory_wav_path_cannot_escape_voicebank_root(tmp_path: Path) -> None:
    root = tmp_path / "voicebank"
    root.mkdir()
    outside = tmp_path / "outside.wav"
    write_pcm_wav(outside, [1000, -1000] * 64)
    (root / "oto.ini").write_text(
        "../outside.wav=あ,0,100,-100,20,10\n", encoding="utf-8"
    )

    analysis = analyze_voicebank(root)

    assert any(issue.code == "wav_path_escape" for issue in analysis.issues)
    assert analysis.summary["errors"] >= 1
    # A file outside the root must not be inspected as a voicebank sample.
    assert analysis.wav_files == ()



def test_symlinked_wav_cannot_escape_voicebank_root(tmp_path: Path) -> None:
    """A relative filename must not bypass root checks through a symlink."""
    root = tmp_path / "voicebank"
    root.mkdir()
    outside = tmp_path / "outside.wav"
    write_pcm_wav(outside, [1000, -1000] * 64)
    try:
        (root / "linked.wav").symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation is unavailable on this platform: {exc}")
    (root / "oto.ini").write_text(
        "linked.wav=あ,0,100,-100,20,10" + chr(10), encoding="utf-8"
    )

    analysis = analyze_voicebank(root)

    assert any(issue.code == "wav_path_escape" for issue in analysis.issues)
    # The target outside the bank must never be opened by the audit pipeline.
    assert analysis.wav_files == ()


def test_cp932_voicebank_paths_and_utf8_bom_prefix_map_are_supported(tmp_path: Path) -> None:
    """Japanese Windows voicebanks may use CP932 while prefix.map has a UTF-8 BOM."""
    root = tmp_path / "voicebank"
    root.mkdir()
    sample_name = "音源.wav"
    write_pcm_wav(root / sample_name, [1200, -1200] * 64)

    # CP932 is common in legacy Japanese UTAU banks; preserve Japanese paths
    # and aliases rather than silently dropping or corrupting these entries.
    (root / "oto.ini").write_bytes(
        f"{sample_name}=あ,0,100,-100,20,10\n".encode("cp932")
    )
    (root / "prefix.map").write_bytes(
        b"\xef\xbb\xbf" + "C4\t-\t_F4\n".encode("utf-8")
    )

    analysis = analyze_voicebank(root)

    assert analysis.entries[0].wav_filename == sample_name
    assert analysis.entries[0].alias == "あ"
    assert analysis.prefix_entries
    assert analysis.prefix_entries[0].boundary == 60
    assert analysis.prefix_entries[0].suffix == "_F4"
    assert analysis.summary["wav_files_checked"] == 1
    assert analysis.summary["wav_files_invalid"] == 0
    assert not any(
        issue.code in {"oto_parse_issue", "prefix_map_parse_issue"}
        for issue in analysis.issues
    )

def test_duplicate_aliases_across_nested_oto_files_remain_ambiguous(
    tmp_path: Path,
) -> None:
    root = tmp_path / "voicebank"
    first = root / "append"
    second = root / "prefix"
    write_pcm_wav(first / "a.wav", [900, -900] * 64)
    write_pcm_wav(second / "a.wav", [1800, -1800] * 64)
    (first / "oto.ini").write_text(
        "a.wav=あ,0,100,-100,20,10\n", encoding="utf-8"
    )
    (second / "oto.ini").write_text(
        "a.wav=あ,0,100,-100,20,10\n", encoding="utf-8"
    )

    analysis = analyze_voicebank(root)
    resolved = resolve_utau_alias(
        "あ", 60, analysis.entries, voicebank_root=root
    )

    assert analysis.summary["oto_files"] == 2
    assert analysis.summary["oto_entries"] == 2
    assert analysis.summary["wav_files_checked"] == 2
    assert analysis.summary["duplicate_alias_groups"] == 1
    assert {entry.wav_filename for entry in analysis.entries} == {
        "append/a.wav",
        "prefix/a.wav",
    }
    assert resolved.status == "ambiguous"
    assert {candidate.wav_path for candidate in resolved.candidates} == {
        (root / "append/a.wav").resolve(),
        (root / "prefix/a.wav").resolve(),
    }
    duplicate_issues = [
        issue for issue in analysis.issues if issue.code == "duplicate_alias"
    ]
    assert len(duplicate_issues) == 1

def test_missing_sample_is_reported_and_cannot_resolve_while_valid_sample_survives(
    tmp_path: Path,
) -> None:
    root = tmp_path / "voicebank"
    root.mkdir()
    write_pcm_wav(root / "valid.wav", [700, -700] * 64)
    (root / "oto.ini").write_text(
        "valid.wav=あ,0,100,-100,20,10\\n"
        "missing.wav=い,0,100,-100,20,10\\n",
        encoding="utf-8",
    )

    analysis = analyze_voicebank(root)

    assert analysis.summary["oto_entries"] == 2
    assert analysis.summary["wav_files_checked"] == 1
    assert analysis.summary["wav_files_invalid"] == 0
    assert any(
        issue.code == "wav_missing" and "missing.wav" in issue.message
        for issue in analysis.issues
    )
    assert {item.path for item in analysis.wav_files} == {"valid.wav"}

    valid = resolve_utau_alias("あ", 60, analysis.entries, voicebank_root=root)
    missing = resolve_utau_alias("い", 60, analysis.entries, voicebank_root=root)
    assert valid.status == "resolved"
    assert valid.candidates[0].wav_path == (root / "valid.wav").resolve()
    assert missing.status == "invalid_sample_path"
    assert missing.candidates == ()
    assert any("missing.wav" in issue for issue in missing.issues)
