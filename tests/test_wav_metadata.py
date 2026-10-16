from __future__ import annotations

from pathlib import Path
import struct

import pytest

from axral_vocal_ai.wav_metadata import inspect_wav


def write_wav(path: Path, *, sample_rate: int = 44100, channels: int = 1,
              bits: int = 16, frames: int = 441, audio_format: int = 1) -> None:
    block_align = channels * bits // 8
    byte_rate = sample_rate * block_align
    data = bytes(frames * block_align)
    fmt = struct.pack("<HHIIHH", audio_format, channels, sample_rate,
                      byte_rate, block_align, bits)
    chunks = b"fmt " + struct.pack("<I", len(fmt)) + fmt
    chunks += b"data" + struct.pack("<I", len(data)) + data
    path.write_bytes(b"RIFF" + struct.pack("<I", len(chunks) + 4) + b"WAVE" + chunks)


def test_inspects_pcm_metadata_without_decoding_samples(tmp_path: Path) -> None:
    path = tmp_path / "sample.wav"
    write_wav(path)

    result = inspect_wav(path)

    assert result.audio_format == "pcm"
    assert result.channels == 1
    assert result.sample_rate == 44100
    assert result.bits_per_sample == 16
    assert result.data_bytes == 882
    assert result.duration_seconds == pytest.approx(0.01)
    assert result.issues == ()


def test_reports_stereo_float_format(tmp_path: Path) -> None:
    path = tmp_path / "float.wav"
    write_wav(path, channels=2, bits=32, audio_format=3)

    result = inspect_wav(path)

    assert result.audio_format == "ieee_float"
    assert result.channels == 2
    assert result.bits_per_sample == 32


def test_rejects_non_wave_and_truncated_headers(tmp_path: Path) -> None:
    path = tmp_path / "bad.wav"
    path.write_bytes(b"not a wave")

    with pytest.raises(ValueError, match="header is truncated"):
        inspect_wav(path)

    path.write_bytes(b"NOPE" + bytes(40))
    with pytest.raises(ValueError, match="RIFF/WAVE"):
        inspect_wav(path)


def test_rejects_missing_data_chunk(tmp_path: Path) -> None:
    path = tmp_path / "no-data.wav"
    fmt = struct.pack("<HHIIHH", 1, 1, 44100, 88200, 2, 16)
    chunk = b"fmt " + struct.pack("<I", len(fmt)) + fmt
    path.write_bytes(b"RIFF" + struct.pack("<I", len(chunk) + 4) + b"WAVE" + chunk)

    with pytest.raises(ValueError, match="data chunk"):
        inspect_wav(path)


def test_reports_declared_riff_size_larger_than_file(tmp_path: Path) -> None:
    path = tmp_path / "truncated.wav"
    write_wav(path)
    raw = bytearray(path.read_bytes())
    struct.pack_into("<I", raw, 4, len(raw) + 100)
    path.write_bytes(raw)

    result = inspect_wav(path)

    assert "riff_size_exceeds_file" in result.issues
