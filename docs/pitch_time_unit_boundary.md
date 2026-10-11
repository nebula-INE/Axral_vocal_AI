# Pitch time-unit boundary

Status: implemented as isolated unit conversion helpers; no renderer adapter is enabled.

## Canonical contract

Axral pitch notes and pitch-delta points use **absolute seconds**. A target
format may require milliseconds, but a unit conversion must be explicit at
that boundary. The functions in `axral_vocal_ai.time_units` convert seconds
and milliseconds without rounding or quantization.

## Invariants

- The conversion is only a unit conversion: it does not change absolute time
  into note-relative time.
- It does not quantize to the native 5 ms frame period, UST ticks, or any
  caller-defined sample grid.
- It does not interpolate, smooth, clamp, reorder, or apply pitch points.
- Non-numeric and non-finite inputs are rejected.
- Negative finite values are preserved rather than silently clamped; callers
  that require non-negative timeline positions must enforce that domain rule
  in their own validated contract.
- The existing Desktop and Web production code remains unchanged.

## Still blocked

This helper does **not** make Desktop and Web pitch data interchangeable.
Before an adapter is enabled, the project must still establish whether each
timestamp is absolute or note-relative, characterize target frame/tick
quantization, and test note starts/ends, rests, shared boundaries, and
round-trips against the real Desktop and Web implementations. Desktop native
automation values also remain distinct from semitone offsets; no conversion
for those raw values is provided here.
