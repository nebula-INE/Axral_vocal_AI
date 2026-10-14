"""Parse UTAU oto.ini entries into an auditable alias inventory.

This module indexes metadata only. It does not load audio, resolve phonemes,
or claim that an alias is acoustically usable.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import PurePosixPath, PureWindowsPath


@dataclass(frozen=True)
class OtoEntry:
    """One parsed oto.ini record; duplicate aliases are intentionally retained."""

    source_line: int
    wav_filename: str
    alias: str
    offset: float
    consonant: float
    cutoff: float
    preutterance: float
    overlap: float


@dataclass(frozen=True)
class OtoParseIssue:
    """A line-level parse problem that should be surfaced to the caller."""

    line_number: int
    message: str
    raw_line: str


@dataclass(frozen=True)
class OtoParseResult:
    entries: tuple[OtoEntry, ...]
    issues: tuple[OtoParseIssue, ...]


def _normalize_relative_wav(filename: str) -> str:
    """Normalize separators while preserving absolute paths for explicit review."""
    value = filename.strip().replace("\\", "/")
    posix = PurePosixPath(value)
    windows = PureWindowsPath(filename.strip())
    if posix.is_absolute() or windows.is_absolute() or windows.drive:
        return value
    normalized = str(posix)
    return "" if normalized == "." else normalized


def parse_oto_ini(content: str) -> OtoParseResult:
    """Parse standard six-parameter oto.ini lines without dropping bad records.

    Expected format: wav=alias,offset,consonant,cutoff,preutterance,overlap.
    Blank lines and comments are ignored. Malformed lines become issues, and
    duplicate aliases remain separate entries so callers can inspect ambiguity.
    """
    if not isinstance(content, str):
        raise TypeError("oto.ini content must be a string")

    entries: list[OtoEntry] = []
    issues: list[OtoParseIssue] = []
    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith(";") or line.startswith("#"):
            continue
        if "=" not in line:
            issues.append(OtoParseIssue(line_number, "Missing '=' separator.", raw_line))
            continue

        wav_raw, value_raw = line.split("=", 1)
        wav_filename = _normalize_relative_wav(wav_raw)
        values = value_raw.split(",")
        if not wav_filename:
            issues.append(OtoParseIssue(line_number, "Missing WAV filename.", raw_line))
            continue
        if len(values) != 6:
            issues.append(
                OtoParseIssue(
                    line_number,
                    f"Expected alias plus five numeric parameters; got {len(values)} fields.",
                    raw_line,
                )
            )
            continue

        alias = values[0].strip()
        if not alias:
            issues.append(OtoParseIssue(line_number, "Alias is empty.", raw_line))
            continue

        try:
            numbers = tuple(float(value.strip()) for value in values[1:])
        except ValueError:
            issues.append(OtoParseIssue(line_number, "A numeric parameter is invalid.", raw_line))
            continue
        if not all(math.isfinite(value) for value in numbers):
            issues.append(OtoParseIssue(line_number, "Numeric parameters must be finite.", raw_line))
            continue

        entries.append(
            OtoEntry(
                source_line=line_number,
                wav_filename=wav_filename,
                alias=alias,
                offset=numbers[0],
                consonant=numbers[1],
                cutoff=numbers[2],
                preutterance=numbers[3],
                overlap=numbers[4],
            )
        )

    return OtoParseResult(entries=tuple(entries), issues=tuple(issues))
