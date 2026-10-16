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
            scale = float(1 << (width * 8 - 1))
            peak = 0
            sum_squares = 0.0
            sample_count = 0
            frames_checked = 0
            clipped = False
            malformed_data: set[str] = set()
            # Bound reads by bytes as well as frames: a malformed file can
            # declare an extreme channel count, making a frame-only limit huge.
            bytes_per_frame = width * max(audio.getnchannels(), 1)
            max_chunk_bytes = 1024 * 1024
            bounded_chunk_frames = max(1, min(chunk_frames, max_chunk_bytes // bytes_per_frame))
            while True:
                raw = audio.readframes(bounded_chunk_frames)
                if not raw:
                    break
                if len(raw) % width:
                    malformed_data.add("incomplete_pcm_sample")
                samples = _decode_pcm(raw, width)
                channels = max(audio.getnchannels(), 1)
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
        return WavSignalAudit("empty", frames_checked, 0.0, 0.0, ("no_audio_samples",))

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
