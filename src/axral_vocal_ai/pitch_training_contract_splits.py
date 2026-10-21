"""Deterministic leakage-safe splits for example-level pitch training records.

This module operates on validated metadata only. It does not read audio, convert
schemas, or touch synthesis/inference runtime code.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import math
from typing import Any, Iterable, Mapping

from .pitch_training_contract import validate_record

_DEFAULT_RATIOS = {"train": 0.8, "validation": 0.1, "test": 0.1}
_SPLIT_ORDER = ("train", "validation", "test")
_OPTIONAL_GROUP_FIELDS = ("project_id", "session_id", "source_group_id")


class PitchTrainingSplitError(ValueError):
    """Raised when example-level records cannot be safely split."""


def _normalized_ratios(ratios: Mapping[str, float] | None) -> dict[str, float]:
    supplied = _DEFAULT_RATIOS if ratios is None else ratios
    if not isinstance(supplied, Mapping) or set(supplied) != set(_SPLIT_ORDER):
        raise PitchTrainingSplitError(
            "ratios must define exactly train, validation, and test"
        )
    normalized: dict[str, float] = {}
    for split in _SPLIT_ORDER:
        value = supplied[split]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise PitchTrainingSplitError(f"ratio for {split} must be finite")
        try:
            number = float(value)
        except (OverflowError, ValueError):
            raise PitchTrainingSplitError(f"ratio for {split} must be finite") from None
        if not math.isfinite(number) or number <= 0:
            raise PitchTrainingSplitError(
                f"ratio for {split} must be finite and greater than zero"
            )
        normalized[split] = number
    total = sum(normalized.values())
    if not math.isfinite(total) or total <= 0:
        raise PitchTrainingSplitError("ratio total must be finite and greater than zero")
    return {split: value / total for split, value in normalized.items()}


def _stable_key(tokens: Iterable[str]) -> str:
    return hashlib.sha256("\n".join(sorted(tokens)).encode("utf-8")).hexdigest()


def assign_example_splits(
    records: Iterable[Mapping[str, Any]],
    ratios: Mapping[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Return copied example-level records with deterministic split assignments.

    Records are kept together when they share voicebank.split_group,
    provenance.source_id, or any populated optional provenance project/session/
    source-group ID. Existing split fields are overwritten. At least three
    independent groups are seeded into distinct splits; groups remain indivisible.
    Every record is validated with the example-level validator before assignment.
    """
    ratio_map = _normalized_ratios(ratios)
    copied: list[dict[str, Any]] = []
    ids: set[str] = set()
    for index, raw in enumerate(records, start=1):
        if not isinstance(raw, Mapping):
            raise PitchTrainingSplitError(f"record {index} must be an object")
        record = dict(raw)
        issues = validate_record(record)
        if issues:
            codes = ", ".join(code for code, _ in issues)
            raise PitchTrainingSplitError(f"record {index} is invalid: {codes}")
        example_id = record["example_id"]
        if example_id in ids:
            raise PitchTrainingSplitError(f"duplicate example_id {example_id!r}")
        ids.add(example_id)
        record["split"] = "train"
        copied.append(record)

    if not copied:
        raise PitchTrainingSplitError("dataset contains no example records")

    parents = list(range(len(copied)))

    def find(item: int) -> int:
        while parents[item] != item:
            parents[item] = parents[parents[item]]
            item = parents[item]
        return item

    def union(left: int, right: int) -> None:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parents[max(root_left, root_right)] = min(root_left, root_right)

    owners: dict[tuple[str, str], int] = {}
    record_tokens: list[list[str]] = []
    for index, record in enumerate(copied):
        provenance = record["provenance"]
        voicebank = record["voicebank"]
        identities = [
            ("voicebank_split_group", voicebank["split_group"].strip()),
            ("source_id", provenance["source_id"].strip()),
        ]
        for field in _OPTIONAL_GROUP_FIELDS:
            value = provenance.get(field)
            if isinstance(value, str) and value.strip():
                identities.append((field, value.strip()))

        tokens = [f"{field}:{value}" for field, value in identities]
        record_tokens.append(tokens)
        for identity in identities:
            if identity in owners:
                union(index, owners[identity])
            else:
                owners[identity] = index

    components: dict[int, list[int]] = defaultdict(list)
    for index in range(len(copied)):
        components[find(index)].append(index)

    groups = []
    for indices in components.values():
        tokens = [token for index in indices for token in record_tokens[index]]
        groups.append((indices, _stable_key(tokens)))
    groups.sort(key=lambda item: (-len(item[0]), item[1]))

    targets = {name: len(copied) * ratio_map[name] for name in _SPLIT_ORDER}
    assigned = {name: 0 for name in _SPLIT_ORDER}
    reserved = min(len(groups), len(_SPLIT_ORDER))
    for group_index, (indices, _) in enumerate(groups[:reserved]):
        split = _SPLIT_ORDER[group_index]
        for record_index in indices:
            copied[record_index]["split"] = split
        assigned[split] += len(indices)

    for indices, _ in groups[reserved:]:
        split = max(
            _SPLIT_ORDER,
            key=lambda name: (targets[name] - assigned[name], -_SPLIT_ORDER.index(name)),
        )
        for record_index in indices:
            copied[record_index]["split"] = split
        assigned[split] += len(indices)

    return copied
