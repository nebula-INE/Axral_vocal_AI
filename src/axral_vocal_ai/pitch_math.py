"""Pure pitch-unit math primitives.

These helpers are deliberately renderer-independent. They do not sample curves,
modify notes, or feed Desktop/Web/WORLD rendering paths.
"""
from __future__ import annotations

import math


def midi_note_to_hz(midi_note: float) -> float:
    """Convert a MIDI note number to equal-tempered frequency (A4 = 440 Hz)."""
    if not math.isfinite(midi_note):
        raise ValueError("midi_note must be finite")
    if not 0.0 <= midi_note <= 127.0:
        raise ValueError("midi_note must be in the MIDI range 0..127")
    return 440.0 * (2.0 ** ((midi_note - 69.0) / 12.0))


def semitone_delta_to_frequency_ratio(delta_semitones: float) -> float:
    """Convert a relative semitone offset to a positive frequency multiplier."""
    if not math.isfinite(delta_semitones):
        raise ValueError("delta_semitones must be finite")
    # Avoid producing infinity from extreme but finite external values.
    exponent = delta_semitones / 12.0
    try:
        ratio = 2.0 ** exponent
    except OverflowError as exc:
        raise ValueError("delta_semitones is outside the representable range") from exc
    if not math.isfinite(ratio) or ratio <= 0.0:
        raise ValueError("delta_semitones is outside the representable range")
    return ratio
