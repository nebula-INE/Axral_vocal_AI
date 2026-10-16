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

def test_handles_unsigned_8_bit_pcm_and_stereo_frames(tmp_path: Path) -> None:
    mono_path = tmp_path / "eight_bit_silence.wav"
    write_pcm(mono_path, [0] * 32, width=1)
    mono = inspect_pcm_signal(mono_path, chunk_frames=3)
    assert mono.status == "ok"
    assert mono.frames_checked == 32
    assert mono.peak_normalized == 0.0
    assert "digital_silence" in mono.issues

    stereo_path = tmp_path / "stereo.wav"
    write_pcm(stereo_path, [1000, -1000, 2000, -2000, 3000, -3000, 4000, -4000],
              width=2, channels=2)
    stereo = inspect_pcm_signal(stereo_path, chunk_frames=1)
    assert stereo.status == "ok"
    assert stereo.frames_checked == 4
    assert stereo.peak_normalized > 0.0
    assert "digital_silence" not in stereo.issues



def test_reports_truncated_pcm_sample_instead_of_silently_ignoring_it(tmp_path: Path) -> None:
    path = tmp_path / "truncated.wav"
    write_pcm(path, [1200], width=2)
    raw = bytearray(path.read_bytes())
    # Declare a four-byte data payload, but leave only three payload bytes.
    # The physical file is truncated by one byte relative to its WAV header.
    raw[40:44] = struct.pack("<I", 4)
    raw[4:8] = struct.pack("<I", len(raw) - 8)
    raw.append(0x7F)
    path.write_bytes(raw)

    result = inspect_pcm_signal(path)
    assert result.status == "ok"
    assert "incomplete_pcm_sample" in result.issues
