import math

import pytest

from axral_vocal_ai.time_units import (
    milliseconds_to_seconds,
    seconds_to_milliseconds,
)


@pytest.mark.parametrize(
    ("seconds", "milliseconds"),
    [
        (0.0, 0.0),
        (0.001, 1.0),
        (0.125, 125.0),
        (1.0, 1000.0),
        (12.3456789, 12345.6789),
        (-0.025, -25.0),
    ],
)
def test_seconds_milliseconds_conversion_is_explicit_and_unquantized(
    seconds: float, milliseconds: float
) -> None:
    assert seconds_to_milliseconds(seconds) == pytest.approx(milliseconds)
    assert milliseconds_to_seconds(milliseconds) == pytest.approx(seconds)


@pytest.mark.parametrize("invalid", [math.nan, math.inf, -math.inf, True, "0.5", None])
def test_seconds_to_milliseconds_rejects_invalid_values(invalid: object) -> None:
    with pytest.raises(ValueError):
        seconds_to_milliseconds(invalid)  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid", [math.nan, math.inf, -math.inf, True, "500", None])
def test_milliseconds_to_seconds_rejects_invalid_values(invalid: object) -> None:
    with pytest.raises(ValueError):
        milliseconds_to_seconds(invalid)  # type: ignore[arg-type]


def test_round_trip_does_not_quantize_to_five_millisecond_frames() -> None:
    # The canonical contract preserves absolute time. Frame-grid conversion
    # belongs to a later, renderer-specific adapter and must not happen here.
    original = 0.037
    converted = milliseconds_to_seconds(seconds_to_milliseconds(original))
    assert converted == pytest.approx(original, abs=1e-12)
    assert seconds_to_milliseconds(original) == pytest.approx(37.0)
