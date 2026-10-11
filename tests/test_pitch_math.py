import math

import pytest

from axral_vocal_ai.pitch_math import (
    midi_note_to_hz,
    semitone_delta_to_frequency_ratio,
)


@pytest.mark.parametrize(
    ("midi_note", "expected_hz"),
    [
        (69.0, 440.0),
        (57.0, 220.0),
        (81.0, 880.0),
        (60.0, 261.6255653005986),
        (69.5, 440.0 * math.sqrt(2.0 ** (1.0 / 12.0))),
        (0.0, 440.0 * (2.0 ** (-69.0 / 12.0))),
        (127.0, 440.0 * (2.0 ** (58.0 / 12.0))),
    ],
)
def test_midi_note_to_hz_reference_values(midi_note: float, expected_hz: float) -> None:
    assert midi_note_to_hz(midi_note) == pytest.approx(expected_hz, rel=1e-12)


@pytest.mark.parametrize("midi_note", [-0.001, 127.001, math.inf, math.nan, -math.inf])
def test_midi_note_to_hz_rejects_invalid_values(midi_note: float) -> None:
    with pytest.raises(ValueError):
        midi_note_to_hz(midi_note)


def test_semitone_delta_to_frequency_ratio_reference_values() -> None:
    assert semitone_delta_to_frequency_ratio(0.0) == pytest.approx(1.0)
    assert semitone_delta_to_frequency_ratio(12.0) == pytest.approx(2.0)
    assert semitone_delta_to_frequency_ratio(-12.0) == pytest.approx(0.5)
    assert semitone_delta_to_frequency_ratio(2.0) == pytest.approx(2.0 ** (2.0 / 12.0))
    assert semitone_delta_to_frequency_ratio(-2.0) == pytest.approx(2.0 ** (-2.0 / 12.0))


@pytest.mark.parametrize("delta", [math.inf, math.nan, -math.inf, 20000.0, -20000.0])
def test_semitone_delta_to_frequency_ratio_rejects_invalid_or_unrepresentable_values(
    delta: float,
) -> None:
    with pytest.raises(ValueError):
        semitone_delta_to_frequency_ratio(delta)


@pytest.mark.parametrize(
    ("midi_note", "delta"),
    [
        (48.0, -2.0),
        (60.0, -0.5),
        (60.0, 0.0),
        (60.0, 0.5),
        (69.0, 2.0),
        (100.0, -1.25),
        (12.25, 1.75),
        (36.5, -1.125),
        (72.75, 0.375),
        (110.0, -2.0),
    ],
)
def test_midi_frequency_and_semitone_ratio_are_consistent(
    midi_note: float, delta: float
) -> None:
    # Independent pure-math invariant: applying a semitone ratio to a base
    # frequency must equal converting the correspondingly shifted MIDI pitch.
    # This is not a renderer adapter and must not be wired into production audio.
    base_hz = midi_note_to_hz(midi_note)
    ratio = semitone_delta_to_frequency_ratio(delta)
    shifted_hz = midi_note_to_hz(midi_note + delta)
    assert base_hz * ratio == pytest.approx(shifted_hz, rel=1e-12)

