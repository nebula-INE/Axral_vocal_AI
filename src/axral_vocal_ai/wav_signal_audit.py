"""Bounded, local waveform-level diagnostics for integer PCM WAV files.

Only a small frame block is read at a time. Audio is never uploaded, copied,
or modified. This is a heuristic signal check, not a phoneme or quality judge.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import struct
import wave
from pathlib import Path


@dataclass(frozen=True)
class WavSignalAudit:
    status: str
    frames_checked: int
    peak_normalized: float | None
    rms_normalized: float | None
    issues: tuple[str, ...] = ()


def _decode_pcm(raw: bytes, sample_width: int) -> list[int]:
    if sample_width == 1:
        return [value - 128 for value in raw]
    if sample_width == 2:
        usable = len(raw) - len(raw) % 2
        return [value[0] for value in struct.iter_unpack("<h", raw[:usable])]
    if sample_width == 3:
        usable = len(raw) - len(raw) % 3
        values = []
        for index in range(0, usable, 3):
            value = int.from_bytes(raw[index:index + 3], "little", signed=False)
            if value & 0x800000:
                value -= 1 << 24
            values.append(value)
        return values
    if sample_width == 4:
        usable = len(raw) - len(raw) % 4
        return [value[0] for value in struct.iter_unpack("<i", raw[:usable])]
    raise ValueError(f"Unsupported PCM sample width: {sample_width} bytes")


def _inspect_data_chunk_layout(path: str | Path, sample_width: int,
                               channels: int) -> set[str]:
    """Inspect RIFF chunk lengths without loading sample data into memory.

    wave.readframes returns only complete declared frames, which can hide a
    physically truncated data chunk. Inspect its boundary separately.
    """
    issues: set[str] = set()
    try:
        with open(path, "rb") as stream:
            stream.seek(0, 2)
            file_size = stream.tell()
            stream.seek(0)
            header = stream.read(12)
            if len(header) != 12 or header[:4] != b"RIFF" or header[8:12] != b"WAVE":
                return issues
            # A chunk is part of the WAV container only if it falls within
            # the RIFF-declared boundary. Bytes physically trailing the RIFF
            # payload must not make an oversized data chunk look complete.
            riff_end = min(file_size, struct.unpack("<I", header[4:8])[0] + 8)
            offset = 12
            while offset + 8 <= riff_end:
                stream.seek(offset)
                chunk_header = stream.read(8)
                if len(chunk_header) != 8:
                    break
                chunk_id = chunk_header[:4]
                declared_size = struct.unpack("<I", chunk_header[4:])[0]
                data_start = offset + 8
                if chunk_id == b"data":
                    available = max(0, min(declared_size, riff_end - data_start))
                    if available < declared_size:
                        issues.add("truncated_data_chunk")
                    if available % sample_width:
                        issues.add("incomplete_pcm_sample")
                    if available % (sample_width * max(channels, 1)):
                        issues.add("incomplete_sample_frame")
                    if declared_size % sample_width:
                        issues.add("declared_data_size_not_sample_aligned")
                    return issues
                offset = data_start + declared_size + (declared_size & 1)
    except OSError:
        return issues
    return issues


def inspect_pcm_signal(path: str | Path, *, near_silence_threshold: float = 0.001,
                        chunk_frames: int = 8192) -> WavSignalAudit:
    """Compute peak/RMS for PCM WAV in bounded chunks, without loading all audio."""
    if not 0.0 <= near_silence_threshold < 1.0:
        raise ValueError("near_silence_threshold must be in [0, 1)")
    if chunk_frames < 1:
        raise ValueError("chunk_frames must be positive")

    try:
        with wave.open(str(path), "rb") as audio:
            if audio.getcomptype() != "NONE":
                return WavSignalAudit("unsupported", 0, None, None, ("compressed_audio_unsupported",))
            width = audio.getsampwidth()
            if width not in (1, 2, 3, 4):
                return WavSignalAudit("unsupported", 0, None, None, ("pcm_sample_width_unsupported",))
            channels = max(audio.getnchannels(), 1)
            malformed_data = _inspect_data_chunk_layout(path, width, channels)
            scale = float(1 << (width * 8 - 1))
            peak = 0
            sum_squares = 0.0
            sample_count = 0
            frames_checked = 0
            clipped = False
            # Bound reads by bytes as well as frames: malformed channel counts
            # must not turn a frame-based limit into an unbounded allocation.
            bytes_per_frame = width * channels
            max_chunk_bytes = 1024 * 1024
            bounded_chunk_frames = max(1, min(chunk_frames, max_chunk_bytes // bytes_per_frame))
            while True:
                raw = audio.readframes(bounded_chunk_frames)
                if not raw:
                    break
                if len(raw) % width:
                    malformed_data.add("incomplete_pcm_sample")
                samples = _decode_pcm(raw, width)
                if len(samples) % channels:
                    malformed_data.add("incomplete_sample_frame")
                if not samples:
                    break
                for sample in samples:
                    magnitude = abs(sample)
                    if magnitude > peak:
                        peak = magnitude
                    if magnitude >= scale - 1:
                        clipped = True
                    normalized = sample / scale
                    sum_squares += normalized * normalized
                sample_count += len(samples)
                frames_checked += len(samples) // channels
    except (wave.Error, EOFError, OSError) as exc:
        return WavSignalAudit("unreadable", 0, None, None, (f"signal_read_failed:{exc}",))

    if sample_count == 0:
        return WavSignalAudit("empty", frames_checked, 0.0, 0.0, tuple(sorted(malformed_data | {"no_audio_samples"})))

    peak_normalized = peak / scale
    rms_normalized = math.sqrt(sum_squares / sample_count)
    issues: list[str] = sorted(malformed_data)
    if peak == 0:
        issues.append("digital_silence")
    elif rms_normalized < near_silence_threshold:
        issues.append("near_silence")
    if clipped:
        issues.append("clipping_suspected")
    return WavSignalAudit("ok", frames_checked, peak_normalized, rms_normalized, tuple(issues))
