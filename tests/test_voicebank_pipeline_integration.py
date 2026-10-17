from __future__ import annotations

import json
from pathlib import Path
import struct
import wave

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
        f"{outside}=あ,0,100,-100,20,10\\n", encoding="utf-8"
    )

    analysis = analyze_voicebank(root)

    assert any(issue.code == "absolute_wav_path" for issue in analysis.issues)
    assert analysis.summary["errors"] >= 1
    # Absolute paths are never accepted as an in-bank relative sample path.
    assert analysis.entries[0].wav_filename == str(outside)
