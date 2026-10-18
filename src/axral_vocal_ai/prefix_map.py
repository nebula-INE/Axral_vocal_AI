"""Conservative parser and mapper for UTAU prefix.map files.

The mapping follows VO-SE_vocal's established lower-boundary convention.
This module only maps aliases; it does not select or render audio samples.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Sequence


_NOTE_TO_SEMITONE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


@dataclass(frozen=True)
class PrefixMapEntry:
    boundary: int
    prefix: str
    suffix: str


@dataclass(frozen=True)
class PrefixMapIssue:
    line_number: int
    message: str
    raw_line: str


@dataclass(frozen=True)
class PrefixMapParseResult:
    entries: tuple[PrefixMapEntry, ...]
    issues: tuple[PrefixMapIssue, ...]


def note_name_to_midi(value: str) -> int | None:
    """Convert note names such as C4, F#4, Bb3, or C-1 to MIDI note numbers."""
    if not isinstance(value, str):
        raise TypeError("note name must be a string")
    match = re.fullmatch(r"([A-Ga-g])([#b]?)(-?\d+)", value.strip())
    if not match:
        return None
    semitone = _NOTE_TO_SEMITONE[match.group(1).upper()]
    if match.group(2) == "#":
        semitone += 1
    elif match.group(2) == "b":
        semitone -= 1
    return (int(match.group(3)) + 1) * 12 + semitone


def parse_prefix_map(text: str) -> PrefixMapParseResult:
    """Parse tab-delimited prefix.map lines and retain line-level diagnostics.

    A two-column row is interpreted as note + suffix (legacy convention).
    Three-column rows are note + prefix + suffix. '-' means an empty field.
    """
    if not isinstance(text, str):
        raise TypeError("prefix.map content must be a string")

    entries: list[PrefixMapEntry] = []
    issues: list[PrefixMapIssue] = []
    first_line_by_boundary: dict[int, int] = {}
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip("\r\n")
        if not line.strip() or line.lstrip().startswith(("#", ";")):
            continue
        parts = line.split("\t") if "\t" in line else re.split(r"\s+", line.strip())
        parts = [part.strip() for part in parts]
        if len(parts) < 2 or len(parts) > 3:
            issues.append(PrefixMapIssue(line_number, "Expected two or three tab-separated fields.", raw))
            continue
        boundary = note_name_to_midi(parts[0])
        if boundary is None or not 0 <= boundary <= 127:
            issues.append(PrefixMapIssue(line_number, "Invalid or out-of-range note boundary.", raw))
            continue
        if boundary in first_line_by_boundary:
            issues.append(
                PrefixMapIssue(
                    line_number,
                    f"Duplicate note boundary {boundary}; the last row wins during selection "
                    f"(first declared on line {first_line_by_boundary[boundary]}).",
                    raw,
                )
            )
        else:
            first_line_by_boundary[boundary] = line_number
        if len(parts) == 2:
            prefix, suffix = "", parts[1]
        else:
            prefix, suffix = parts[1], parts[2]
        prefix = "" if prefix == "-" else prefix
        suffix = "" if suffix == "-" else suffix
        entries.append(PrefixMapEntry(boundary, prefix, suffix))

    entries.sort(key=lambda item: item.boundary)
    return PrefixMapParseResult(tuple(entries), tuple(issues))


def select_prefix_map(entries: Sequence[PrefixMapEntry], note_num: int) -> PrefixMapEntry | None:
    """Select the last mapping whose lower boundary is <= the requested MIDI note."""
    if not entries:
        return None
    tone = max(0, min(127, int(round(note_num))))
    selected = None
    # Callers may construct entries directly rather than using parse_prefix_map().
    # Sort stably so unsorted inputs still follow lower-boundary semantics and
    # the last declared row wins when boundaries are duplicated.
    for entry in sorted(entries, key=lambda item: item.boundary):
        if entry.boundary > tone:
            break
        selected = entry
    return selected


def map_alias(alias: str, note_num: int, entries: Sequence[PrefixMapEntry]) -> str:
    """Apply the selected prefix/suffix without duplicating already-present parts."""
    mapping = select_prefix_map(entries, note_num)
    if mapping is None:
        return alias
    mapped = alias
    if mapping.prefix and not mapped.startswith(mapping.prefix):
        mapped = mapping.prefix + mapped
    if mapping.suffix and not mapped.endswith(mapping.suffix):
        mapped += mapping.suffix
    return mapped
