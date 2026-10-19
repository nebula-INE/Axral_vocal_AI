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
    # Declare a four-byte data payload, but keep only three payload bytes
    # inside the RIFF container. The last byte is a partial 16-bit PCM sample.
    raw[40:44] = struct.pack("<I", 4)
    raw.append(0x7F)
    raw[4:8] = struct.pack("<I", len(raw) - 8)
    path.write_bytes(raw)

    result = inspect_pcm_signal(path)
    assert result.status == "ok"
    assert "incomplete_pcm_sample" in result.issues



def test_flags_near_silence_without_calling_it_digital_silence(tmp_path: Path) -> None:
    path = tmp_path / "quiet.wav"
    write_pcm(path, [1, -1, 2, -2] * 20, width=2)
    result = inspect_pcm_signal(path, near_silence_threshold=0.001)
    assert result.status == "ok"
    assert result.rms_normalized is not None
    assert 0.0 < result.rms_normalized < 0.001
    assert "near_silence" in result.issues
    assert "digital_silence" not in result.issues


def test_supports_32_bit_pcm_and_bounded_chunk_reads(tmp_path: Path) -> None:
    path = tmp_path / "32_bit.wav"
    write_pcm(path, [0, (1 << 30), -(1 << 30), (1 << 31) - 1], width=4)
    result = inspect_pcm_signal(path, chunk_frames=1)
    assert result.status == "ok"
    assert result.frames_checked == 4
    assert result.peak_normalized == ((1 << 31) - 1) / float(1 << 31)
    assert "clipping_suspected" in result.issues


def test_reports_truncated_stereo_sample_frame(tmp_path: Path) -> None:
    path = tmp_path / "truncated_stereo.wav"
    write_pcm(path, [100, -100, 200, -200], width=2, channels=2)
    raw = bytearray(path.read_bytes())
    # Header declares six payload bytes, but truncate the physical payload to five.
    raw[40:44] = struct.pack("<I", 6)
    raw = raw[:49]  # 44-byte header plus five payload bytes
    raw[4:8] = struct.pack("<I", len(raw) - 8)
    path.write_bytes(raw)

    result = inspect_pcm_signal(path)
    assert result.status == "ok"
    assert "truncated_data_chunk" in result.issues
    assert "incomplete_pcm_sample" in result.issues
    assert "incomplete_sample_frame" in result.issues


def test_rejects_non_riff_input_as_unreadable(tmp_path: Path) -> None:
    path = tmp_path / "not_a_wave.wav"
    path.write_bytes(b"not a RIFF/WAVE file")
    result = inspect_pcm_signal(path)
    assert result.status == "unreadable"

def test_data_chunk_must_fit_inside_declared_riff_boundary(tmp_path: Path) -> None:
    path = tmp_path / "trailing_data_outside_riff.wav"
    write_pcm(path, [1200, -1200], width=2)
    raw = bytearray(path.read_bytes())
    # Keep the physical samples after the data header, but declare the RIFF
    # container to end immediately before those samples.
    raw[4:8] = struct.pack("<I", 36)
    path.write_bytes(raw)

    result = inspect_pcm_signal(path)

    assert "truncated_data_chunk" in result.issues


def test_does_not_audit_physical_bytes_outside_riff_container(tmp_path: Path) -> None:
    path = tmp_path / "outside-riff.wav"
    write_pcm(path, [1200, -1200], width=2)
    raw = bytearray(path.read_bytes())
    # Keep non-silent sample bytes physically present, but exclude the entire
    # data payload from the RIFF container's declared boundary.
    raw[4:8] = struct.pack("<I", 36)
    path.write_bytes(raw)

    result = inspect_pcm_signal(path)

    assert result.status == "malformed"
    assert result.frames_checked == 0
    assert result.peak_normalized is None
    assert "data_payload_outside_riff_boundary" in result.issues
