from __future__ import annotations

from pathlib import Path
import struct
import wave

from axral_vocal_ai.wav_signal_audit import inspect_pcm_signal


def write_pcm(path: Path, samples: list[int], *, width: int = 2, channels: int = 1) -> None:
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(channels)
        audio.setsampwidth(width)
        audio.setframerate(44100)
        if width == 1:
            raw = bytes(sample + 128 for sample in samples)
        elif width == 2:
            raw = struct.pack("<" + "h" * len(samples), *samples)
        elif width == 3:
            raw = b"".join(sample.to_bytes(3, "little", signed=True) for sample in samples)
        else:
            raw = struct.pack("<" + "i" * len(samples), *samples)
        audio.writeframes(raw)


def test_detects_digital_silence(tmp_path: Path) -> None:
    path = tmp_path / "silent.wav"
    write_pcm(path, [0] * 441)
    result = inspect_pcm_signal(path)
    assert result.status == "ok"
    assert result.frames_checked == 441
    assert result.peak_normalized == 0.0
    assert result.rms_normalized == 0.0
    assert "digital_silence" in result.issues


def test_measures_non_silent_pcm(tmp_path: Path) -> None:
    path = tmp_path / "voice.wav"
    write_pcm(path, [1000, -1000, 2000, -2000] * 100)
    result = inspect_pcm_signal(path)
    assert result.status == "ok"
    assert result.peak_normalized > 0.0
    assert result.rms_normalized > 0.0
    assert "digital_silence" not in result.issues


def test_detects_clipping_and_supports_24_bit(tmp_path: Path) -> None:
    path = tmp_path / "clipped.wav"
    write_pcm(path, [0, (1 << 23) - 1, -(1 << 23)], width=3)
    result = inspect_pcm_signal(path)
    assert result.status == "ok"
    assert "clipping_suspected" in result.issues


def test_invalid_threshold_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "sample.wav"
    write_pcm(path, [0, 1])
    try:
        inspect_pcm_signal(path, near_silence_threshold=1.0)
    except ValueError as exc:
        assert "near_silence_threshold" in str(exc)
    else:
        raise AssertionError("invalid threshold should raise ValueError")
