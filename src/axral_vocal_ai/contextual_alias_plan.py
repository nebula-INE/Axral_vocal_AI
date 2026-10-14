"""Explicit CV, VCV, and CVVC alias strategies for Japanese mora sequences.

Alias spellings differ between voicebanks. Caller-provided templates and an
explicit mora-to-vowel map avoid assuming a universal VCV/CVVC convention.
This module plans lookups only; it does not render audio.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping, Sequence

from axral_vocal_ai.oto_inventory import OtoEntry
from axral_vocal_ai.prefix_map import PrefixMapEntry
from axral_vocal_ai.voicebank_alias import AliasResolution, resolve_utau_alias

AliasStrategy = Literal["cv", "vcv", "cvvc"]


@dataclass(frozen=True)
class AliasConvention:
    """Voicebank-specific alias spelling rules.

    Templates may use {current} and, where applicable, {previous_vowel}.
    For VCV/CVVC, vowel_map must explicitly map each preceding mora to the
    vowel token expected by this voicebank. CVVC emits onset and transition
    lookups after the first note. No convention is inferred from inventory.
    """

    strategy: AliasStrategy
    initial_template: str = "{current}"
    cv_template: str = "{current}"
    vcv_template: str = "{previous_vowel} {current}"
    cvvc_onset_template: str = "{current}"
    cvvc_transition_template: str = "{previous_vowel} {current}"
    vowel_map: Mapping[str, str] | None = None


@dataclass(frozen=True)
class PlannedAlias:
    """One alias lookup requested for a note, with its role made explicit."""

    note_index: int
    note_num: int
    mora: str
    role: str
    requested_alias: str
    resolution: AliasResolution


@dataclass(frozen=True)
class ContextualAliasPlan:
    """Auditable alias lookups for a mora-aligned note sequence."""

    status: str
    strategy: str
    morae: tuple[str, ...]
    note_numbers: tuple[int, ...]
    aliases: tuple[PlannedAlias, ...] = ()
    warnings: tuple[str, ...] = ()


def _format(template: str, current: str, previous_vowel: str | None = None) -> str:
    values = {"current": current, "previous_vowel": previous_vowel or ""}
    try:
        alias = template.format(**values).strip()
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Invalid alias template {template!r}: {exc}") from exc
    if not alias:
        raise ValueError("Alias templates must produce a non-empty alias")
    return alias


def plan_contextual_aliases(
    morae: Sequence[str],
    note_numbers: Sequence[int],
    oto_entries: Sequence[OtoEntry],
    convention: AliasConvention,
    prefix_entries: Sequence[PrefixMapEntry] = (),
    voicebank_root: str | Path | None = None,
) -> ContextualAliasPlan:
    """Plan CV, VCV, or CVVC lookups using explicit voicebank conventions.

    One mora is aligned to each MIDI note. A count mismatch or missing
    previous-vowel mapping rejects the whole plan rather than returning
    partial results.
    """
    units, notes = tuple(morae), tuple(note_numbers)
    if convention.strategy not in ("cv", "vcv", "cvvc"):
        raise ValueError(f"Unsupported alias strategy: {convention.strategy!r}")
    if len(units) != len(notes):
        return ContextualAliasPlan(
            "note_mora_count_mismatch", convention.strategy, units, notes,
            warnings=(f"Expected one note per mora; received {len(units)} morae and {len(notes)} notes.",),
        )
    if not units:
        return ContextualAliasPlan(
            "empty", convention.strategy, units, notes,
            warnings=("No morae were supplied.",),
        )

    vowels = convention.vowel_map or {}
    if convention.strategy in ("vcv", "cvvc"):
        missing = tuple(dict.fromkeys(m for m in units[:-1] if not vowels.get(m)))
        if missing:
            return ContextualAliasPlan(
                "needs_review", convention.strategy, units, notes,
                warnings=("Explicit previous-vowel mapping is missing for: " + ", ".join(missing),),
            )

    planned: list[PlannedAlias] = []
    for index, (mora, note_num) in enumerate(zip(units, notes)):
        if index == 0:
            roles = (("initial", _format(convention.initial_template, mora)),)
        elif convention.strategy == "cv":
            roles = (("cv", _format(convention.cv_template, mora)),)
        else:
            previous_vowel = vowels[units[index - 1]]
            if convention.strategy == "vcv":
                roles = (("vcv", _format(convention.vcv_template, mora, previous_vowel)),)
            else:
                roles = (
                    ("cvvc_onset", _format(convention.cvvc_onset_template, mora, previous_vowel)),
                    ("vc_transition", _format(convention.cvvc_transition_template, mora, previous_vowel)),
                )
        for role, alias in roles:
            resolution = resolve_utau_alias(
                alias, note_num, oto_entries, prefix_entries=prefix_entries,
                voicebank_root=voicebank_root,
            )
            planned.append(PlannedAlias(index, note_num, mora, role, alias, resolution))

    unresolved = sum(item.resolution.status != "resolved" for item in planned)
    return ContextualAliasPlan(
        "resolved" if unresolved == 0 else "needs_review",
        convention.strategy, units, notes, tuple(planned),
        () if unresolved == 0 else (
            f"{unresolved} of {len(planned)} alias lookups need review; no ambiguous candidate was selected.",
        ),
    )
