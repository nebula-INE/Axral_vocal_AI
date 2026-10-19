"""Conservative bridge from an explicit Japanese reading to UTAU aliases.

The baseline contract is one mora per note. It intentionally does not invent
kanji readings or infer CV/VCV/CVVC transitions; callers must opt into this
simple alignment and review non-resolved alias results.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from axral_vocal_ai.japanese_mora import segment_japanese_mora
from axral_vocal_ai.oto_inventory import OtoEntry
from axral_vocal_ai.prefix_map import PrefixMapEntry
from axral_vocal_ai.voicebank_alias import AliasResolution, resolve_utau_alias


@dataclass(frozen=True)
class MoraAliasPlan:
    """A reading's mora segmentation and per-note alias lookup results."""

    original_reading: str
    normalized_reading: str
    morae: tuple[str, ...]
    status: str
    note_numbers: tuple[int, ...]
    resolutions: tuple[AliasResolution, ...] = ()
    warnings: tuple[str, ...] = ()


def plan_mora_aliases(
    reading: str,
    note_numbers: Sequence[int],
    oto_entries: Sequence[OtoEntry],
    prefix_entries: Sequence[PrefixMapEntry] = (),
    voicebank_root: str | Path | None = None,
) -> MoraAliasPlan:
    """Resolve an explicitly supplied kana reading against note-specific aliases.

    Each mora is matched to the corresponding MIDI note number. If the reading
    contains kanji/unsupported characters, or the number of notes differs from
    the number of morae, no partial alias plan is emitted. This conservative
    baseline is for CV-style one-mora-per-note mapping; it is not a CV/VCV/CVVC
    transition planner.
    """
    segmented = segment_japanese_mora(reading)
    notes = tuple(note_numbers)

    if segmented.status != "segmented":
        return MoraAliasPlan(
            original_reading=reading,
            normalized_reading=segmented.normalized,
            morae=segmented.morae,
            status=segmented.status,
            note_numbers=notes,
            warnings=segmented.warnings,
        )

    if len(notes) != len(segmented.morae):
        return MoraAliasPlan(
            original_reading=reading,
            normalized_reading=segmented.normalized,
            morae=segmented.morae,
            status="note_mora_count_mismatch",
            note_numbers=notes,
            warnings=(
                f"Expected one MIDI note per mora: {len(segmented.morae)} morae, "
                f"but received {len(notes)} notes. No aliases were resolved.",
            ),
        )

    resolutions = tuple(
        resolve_utau_alias(
            mora,
            note_num,
            oto_entries,
            prefix_entries=prefix_entries,
            voicebank_root=voicebank_root,
        )
        for mora, note_num in zip(segmented.morae, notes)
    )
    unresolved = sum(result.status != "resolved" for result in resolutions)
    status = "resolved" if unresolved == 0 else "needs_review"
    warnings = () if unresolved == 0 else (
        f"{unresolved} of {len(resolutions)} mora aliases need review; "
        "inspect each resolution's status and issues.",
    )
    return MoraAliasPlan(
        original_reading=reading,
        normalized_reading=segmented.normalized,
        morae=segmented.morae,
        status=status,
        note_numbers=notes,
        resolutions=resolutions,
        warnings=warnings,
    )
