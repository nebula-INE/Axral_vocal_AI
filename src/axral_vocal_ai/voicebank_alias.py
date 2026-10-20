"""Integrate UTAU prefix mapping with an oto.ini alias inventory.

This module deliberately returns every matching sample instead of choosing an
arbitrary duplicate alias. Filesystem access is optional; when a voicebank root
is supplied, candidate paths are confined to that root and checked for files.
It does not decode audio or synthesize sound.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Sequence

from axral_vocal_ai.oto_inventory import OtoEntry
from axral_vocal_ai.prefix_map import PrefixMapEntry, map_alias


@dataclass(frozen=True)
class AliasCandidate:
    """One matching oto.ini entry and its validated WAV path, if checked."""

    entry: OtoEntry
    wav_path: Path | None = None


@dataclass(frozen=True)
class AliasResolution:
    """Auditable result; duplicate aliases remain explicit."""

    requested_alias: str
    mapped_alias: str
    status: str
    candidates: tuple[AliasCandidate, ...]
    issues: tuple[str, ...] = ()


def _safe_wav_path(root: Path, filename: str) -> Path | None:
    """Resolve a WAV path only if it stays inside the voicebank root."""
    if not filename or Path(filename).is_absolute():
        return None
    # PureWindowsPath catches drive paths even when running on POSIX.
    from pathlib import PureWindowsPath

    windows_path = PureWindowsPath(filename)
    if windows_path.is_absolute() or windows_path.drive:
        return None
    resolved_root = root.expanduser().resolve()
    candidate = (resolved_root / filename).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError:
        return None
    return candidate


def resolve_utau_alias(
    alias: str,
    note_num: int,
    oto_entries: Sequence[OtoEntry],
    prefix_entries: Sequence[PrefixMapEntry] = (),
    voicebank_root: str | Path | None = None,
) -> AliasResolution:
    """Map an alias for a note and return all matching oto.ini records.

    If `voicebank_root` is omitted, this performs metadata-only resolution.
    If supplied, paths escaping the root, absolute paths, and missing files are
    excluded and explained in `issues`. Duplicate valid entries are never
    silently collapsed; the caller must decide how to handle ambiguity.
    """
    if not isinstance(alias, str):
        raise TypeError("alias must be a string")
    if not isinstance(note_num, (int, float)) or isinstance(note_num, bool):
        raise TypeError("note_num must be a MIDI note number")
    try:
        numeric_note = float(note_num)
    except (OverflowError, ValueError) as exc:
        raise ValueError("note_num must be a finite MIDI note number between 0 and 127") from exc
    if not math.isfinite(numeric_note) or not 0 <= numeric_note <= 127:
        raise ValueError("note_num must be a finite MIDI note number between 0 and 127")
    mapped_alias = map_alias(alias, int(round(numeric_note)), prefix_entries)
    matching = [entry for entry in oto_entries if entry.alias == mapped_alias]
    issues: list[str] = []
    candidates: list[AliasCandidate] = []

    if voicebank_root is None:
        candidates = [AliasCandidate(entry) for entry in matching]
    else:
        root = Path(voicebank_root)
        for entry in matching:
            path = _safe_wav_path(root, entry.wav_filename)
            if path is None:
                issues.append(
                    f"Line {entry.source_line}: WAV path is absolute or escapes the voicebank root."
                )
                continue
            if not path.is_file():
                issues.append(f"Line {entry.source_line}: WAV file does not exist: {entry.wav_filename}")
                continue
            candidates.append(AliasCandidate(entry, path))

    if len(candidates) == 1:
        status = "resolved"
    elif len(candidates) > 1:
        status = "ambiguous"
    elif matching and voicebank_root is not None:
        status = "invalid_sample_path"
    else:
        status = "missing_alias"

    if status == "ambiguous":
        issues.append("Multiple valid oto.ini records match this alias; no candidate was selected.")
    elif status == "missing_alias":
        issues.append(f"No oto.ini record matches alias {mapped_alias!r}.")
    return AliasResolution(
        requested_alias=alias,
        mapped_alias=mapped_alias,
        status=status,
        candidates=tuple(candidates),
        issues=tuple(issues),
    )
