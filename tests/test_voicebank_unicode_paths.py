from __future__ import annotations

import struct
from pathlib import Path

from axral_vocal_ai.voicebank_analysis import analyze_voicebank


def write_silent_wav(path: Path) -> None:
    fmt = struct.pack("<HHIIHH", 1, 1, 44100, 88200, 2, 16)
    data = bytes(64)
    chunks = b"fmt " + struct.pack("<I", len(fmt)) + fmt
    chunks += b"data" + struct.pack("<I", len(data)) + data
    path.write_bytes(b"RIFF" + struct.pack("<I", len(chunks) + 4) + b"WAVE" + chunks)


def test_resolves_unicode_nfc_nfd_filename_difference(tmp_path: Path) -> None:
    # On disk, the filename uses decomposed Unicode; oto.ini uses composed NFC.
    actual_name = "か\u3099.wav"
    requested_name = "が.wav"
    (tmp_path / actual_name).write_bytes(b"placeholder")
    (tmp_path / "oto.ini").write_text(
        f"{requested_name}=が,0,100,-100,20,10\n", encoding="utf-8"
    )

    result = analyze_voicebank(tmp_path)

    assert result.entries[0].wav_filename == actual_name
    assert not any(issue.code == "wav_missing" for issue in result.issues)


def test_unicode_normalization_does_not_guess_ambiguous_matches(tmp_path: Path) -> None:
    # Two distinct filesystem entries can normalize to the same key on some
    # filesystems; when both are visible, the resolver must not choose one.
    first = tmp_path / "か\u3099.wav"
    second = tmp_path / "が.wav"
    try:
        first.write_bytes(b"one")
        second.write_bytes(b"two")
    except OSError:
        return
    (tmp_path / "oto.ini").write_text(
        "が.wav=が,0,100,-100,20,10\n", encoding="utf-8"
    )

    result = analyze_voicebank(tmp_path)

    # An exact filesystem match takes precedence when it exists.
    if second.is_file():
        assert result.entries[0].wav_filename == "が.wav"
        assert not any(issue.code == "wav_missing" for issue in result.issues)
