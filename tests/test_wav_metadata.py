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
    assert result.duration_seconds is None

def test_reports_data_chunk_larger_than_declared_riff_boundary(tmp_path: Path) -> None:
    path = tmp_path / "oversized-data.wav"
    fmt = struct.pack("<HHIIHH", 1, 1, 44100, 88200, 2, 16)
    fmt_chunk = b"fmt " + struct.pack("<I", len(fmt)) + fmt
    data_header = b"data" + struct.pack("<I", 4096)
    # The RIFF boundary ends immediately after the data header, so the
    # declared payload is not part of the container even if bytes follow it.
    riff_payload = b"WAVE" + fmt_chunk + data_header
    trailing = bytes(4096)
    path.write_bytes(b"RIFF" + struct.pack("<I", len(riff_payload)) + riff_payload + trailing)

    result = inspect_wav(path)

    assert "chunk_size_exceeds_riff_boundary" in result.issues
    assert result.data_bytes == 4096
    assert result.duration_seconds is None


def test_reports_missing_padding_for_odd_sized_data_chunk(tmp_path: Path) -> None:
    path = tmp_path / "missing-padding.wav"
    fmt = struct.pack("<HHIIHH", 1, 1, 44100, 88200, 2, 16)
    fmt_chunk = b"fmt " + struct.pack("<I", len(fmt)) + fmt
    # The odd-sized data chunk ends at the declared RIFF boundary without
    # its required pad byte.
    data_chunk = b"data" + struct.pack("<I", 1) + b"x"
    chunks = fmt_chunk + data_chunk
    path.write_bytes(b"RIFF" + struct.pack("<I", len(chunks) + 4) + b"WAVE" + chunks)

    result = inspect_wav(path)

    assert "missing_chunk_padding" in result.issues
    assert "data_size_not_aligned_to_sample_frames" in result.issues

def test_does_not_parse_chunks_after_a_chunk_crosses_riff_boundary(tmp_path: Path) -> None:
    path = tmp_path / "fmt-crosses-boundary.wav"
    fmt = struct.pack("<HHIIHH", 1, 1, 44100, 88200, 2, 16)
    # A fmt chunk declares more bytes than the RIFF container allows. The
    # physically present bytes after the boundary must not make this valid.
    fmt_header = b"fmt " + struct.pack("<I", len(fmt) + 16)
    data_chunk = b"data" + struct.pack("<I", 4) + bytes(4)
    riff_payload = b"WAVE" + fmt_header + fmt + data_chunk
    declared_riff_size = 4 + len(fmt_header) + len(fmt)
    path.write_bytes(
        b"RIFF" + struct.pack("<I", declared_riff_size) + riff_payload + bytes(16)
    )

    with pytest.raises(ValueError, match="data chunk"):
        inspect_wav(path)

