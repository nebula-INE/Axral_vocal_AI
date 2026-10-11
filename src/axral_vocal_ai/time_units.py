"""Explicit time-unit conversions for pitch-adapter boundaries.

Axral's canonical pitch contract uses absolute seconds. Desktop/Web APIs may
use milliseconds at specific boundaries. These helpers only convert units:
they do not quantize to frames/ticks, shift note-relative timestamps, clamp
values, interpolate curves, or change any renderer behavior.
"""
from __future__ import annotations

import math


def _finite_time(value: float, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def _finite_result(value: float, *, name: str) -> float:
    if not math.isfinite(value):
        raise ValueError(f"converted {name} is outside the finite numeric range")
    return value


def seconds_to_milliseconds(time_sec: float) -> float:
    """Convert an absolute time from seconds to milliseconds without quantizing."""
    seconds = _finite_time(time_sec, name="time_sec")
    return _finite_result(seconds * 1000.0, name="time_ms")


def milliseconds_to_seconds(time_ms: float) -> float:
    """Convert an absolute time from milliseconds to seconds without quantizing."""
    milliseconds = _finite_time(time_ms, name="time_ms")
    return _finite_result(milliseconds / 1000.0, name="time_sec")
