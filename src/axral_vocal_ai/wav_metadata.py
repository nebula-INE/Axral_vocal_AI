"""Read-only RIFF/WAVE header inspection for UTAU sample diagnostics.

This module reads chunk headers and format metadata only. It never decodes,
uploads, copies, or modifies audio samples.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct


@dataclass(frozen=True)
class WavMetadata:
    path: str
    file_size_bytes: int
    container: str
    audio_format_code: int
    audio_format: str
    channels: int
    sample_rate: int
    byte_rate: int
    block_align: int
    bits_per_sample: int
    data_bytes: int
    duration_seconds: float | None
    issues: tuple[str, ...]

    @property
    def is_pcm(self) -> bool:
        return self.audio_format_code == 1

    @property
    def is_float(self) -> bool:
        return self.audio_format_code == 3


_FORMAT_NAMES = {
    1: "pcm",
    3: "ieee_float",
    6: "alaw",
    7: "mulaw",
    65534: "extensible",
}


def inspect_wav(path: str | Path) -> WavMetadata:
    """Inspect RIFF/WAVE metadata without decoding waveform samples.

    Raises ValueError for malformed or unsupported containers. WAVE_FORMAT
    values other than PCM/IEEE float are returned with an explicit format name
    so callers can decide whether the target renderer supports them.
    """
    wav_path = Path(path)
    file_size = wav_path.stat().st_size
    issues: list[str] = []

    with wav_path.open("rb") as stream:
        header = stream.read(12)
        if len(header) != 12:
            raise ValueError("WAV header is truncated")
        container, riff_size, wave_id = struct.unpack("<4sI4s", header)
        if container != b"RIFF" or wave_id != b"WAVE":
            raise ValueError("Expected a little-endian RIFF/WAVE file")
        if riff_size + 8 > file_size:
            issues.append("riff_size_exceeds_file")
        elif riff_size + 8 < file_size:
            issues.append("trailing_bytes_after_riff")

        fmt: tuple[int, int, int, int, int, int] | None = None
        data_bytes: int | None = None
        remaining = min(file_size, riff_size + 8) - 12
        while remaining >= 8:
            chunk_header = stream.read(8)
            if len(chunk_header) != 8:
                raise ValueError("WAV chunk header is truncated")
            chunk_id, chunk_size = struct.unpack("<4sI", chunk_header)
            remaining -= 8
            available = min(chunk_size, max(remaining, 0))
            if chunk_id == b"fmt ":
                if chunk_size < 16:
                    raise ValueError("WAV fmt chunk is shorter than 16 bytes")
                payload = stream.read(min(chunk_size, 40))
                if len(payload) < 16:
                    raise ValueError("WAV fmt chunk is truncated")
                audio_format, channels, sample_rate, byte_rate, block_align, bits = struct.unpack(
                    "<HHIIHH", payload[:16]
                )
                if audio_format == 65534 and len(payload) >= 40:
                    # WAVE_FORMAT_EXTENSIBLE embeds the subtype GUID. The first
                    # two bytes identify PCM (1) or IEEE float (3).
                    subtype = struct.unpack("<H", payload[24:26])[0]
                    if subtype in (1, 3):
                        audio_format = subtype
                fmt = (audio_format, channels, sample_rate, byte_rate, block_align, bits)
                stream.seek(chunk_size - len(payload), 1)
            elif chunk_id == b"data":
                data_bytes = chunk_size
                stream.seek(chunk_size, 1)
            else:
                stream.seek(chunk_size, 1)

            padded_size = chunk_size + (chunk_size & 1)
            if padded_size > remaining:
                if chunk_size > remaining:
                    issues.append("chunk_size_exceeds_riff_boundary")
                    break
                # The odd-size pad byte is absent at the declared boundary.
                issues.append("missing_chunk_padding")
                break
            if chunk_size > remaining:
                issues.append("chunk_truncated")
                break
            if chunk_size & 1:
                stream.seek(1, 1)
            remaining -= padded_size

    if fmt is None:
        raise ValueError("WAV fmt chunk was not found")
    if data_bytes is None:
        raise ValueError("WAV data chunk was not found")

    audio_format, channels, sample_rate, byte_rate, block_align, bits = fmt
    if channels <= 0:
        issues.append("invalid_channel_count")
    if sample_rate <= 0:
        issues.append("invalid_sample_rate")
    if byte_rate <= 0:
        issues.append("invalid_byte_rate")
    if block_align <= 0:
        issues.append("invalid_block_align")
    if bits <= 0:
        issues.append("invalid_bits_per_sample")
    if block_align > 0 and data_bytes % block_align:
        issues.append("data_size_not_aligned_to_sample_frames")

    duration = data_bytes / byte_rate if byte_rate > 0 else None
    return WavMetadata(
        path=wav_path.as_posix(),
        file_size_bytes=file_size,
        container="riff_wave",
        audio_format_code=audio_format,
        audio_format=_FORMAT_NAMES.get(audio_format, f"unknown_{audio_format}"),
        channels=channels,
        sample_rate=sample_rate,
        byte_rate=byte_rate,
        block_align=block_align,
        bits_per_sample=bits,
        data_bytes=data_bytes,
        duration_seconds=duration,
        issues=tuple(issues),
    )
