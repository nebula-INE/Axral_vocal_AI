"""Build a compact profile from VO-SE_vocal's existing OtoParser.

This module does not parse oto.ini or prefix.map itself. Pass an already-loaded
parser object so the established resolver remains authoritative.
"""
from __future__ import annotations

import os
import re
from typing import Any, Iterable, Optional, Sequence

from axral_vocal_ai.contracts import VoicebankProfile

_PITCH_FOLDER = re.compile(r"^[A-Ga-g][#b]?-?\d+$")


def _alias_tokens(alias: str) -> tuple[str, ...]:
    """Extract observable alias tokens without claiming canonical phonemes."""
    lyric = alias.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not lyric:
        return ()
    parts = lyric.split()
    if not parts:
        return ()
    # For common VCV aliases such as "a い", the final token is the target
    # lyric. This is an inventory hint, not a phoneme normalization rule.
    token = parts[-1]
    if _PITCH_FOLDER.fullmatch(token):
        return ()
    return (token,)


def build_voicebank_profile(
    oto_parser: Any,
    *,
    parser_version: Optional[str] = None,
    format_hints: Iterable[str] = (),
    pitch_bank_boundaries: Sequence[float] = (),
) -> VoicebankProfile:
    """Summarize an already-loaded OtoParser without exporting local paths.

    Expected public methods are all_aliases(), get(alias), and has_vcv().
    A sample is counted only when the parser resolves it to an existing file.
    Absolute paths are transient deduplication keys only and are never returned.
    PrefixMap boundaries are passed explicitly by the caller; this adapter does
    not inspect parser internals or duplicate PrefixMap parsing logic.
    """
    aliases = list(oto_parser.all_aliases())
    tokens: set[str] = set()
    sample_refs: set[str] = set()
    hints = set(format_hints)

    if oto_parser.has_vcv():
        hints.add("vcv_aliases")
    if any(" " in alias or "_" in alias for alias in aliases):
        hints.add("contextual_aliases")
    if any("/" in alias or "\\" in alias for alias in aliases):
        hints.add("folder_qualified_aliases")
    if pitch_bank_boundaries:
        hints.add("multipitch")

    for alias in aliases:
        tokens.update(_alias_tokens(alias))
        entry = oto_parser.get(alias)
        if entry is None:
            continue

        # OtoParser.wav_path deliberately returns a predictable candidate path
        # even if the WAV is missing. Verify existence before counting it.
        wav_path = getattr(entry, "wav_path", None)
        if not isinstance(wav_path, (str, os.PathLike)) or not wav_path:
            continue
        try:
            if not os.path.isfile(wav_path):
                continue
            sample_refs.add(os.path.normcase(os.path.realpath(wav_path)))
        except (OSError, TypeError, ValueError):
            continue

    return VoicebankProfile(
        alias_count=len(aliases),
        sample_count=len(sample_refs),
        phoneme_inventory=tuple(sorted(tokens)),
        pitch_bank_boundaries=tuple(pitch_bank_boundaries),
        parser_version=parser_version,
        format_hints=tuple(sorted(hints)),
    )
