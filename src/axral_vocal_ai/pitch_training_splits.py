"""Deterministic group-aware split assignment for legacy training manifests.

This module handles metadata only. It never reads audio or touches model/runtime
code. Voicebanks and source groups are indivisible to prevent dataset leakage.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import math
from typing import Any, Iterable, Mapping

from .training_data import DatasetValidationError, SPLITS, validate_record, validate_records

_DEFAULT_RATIOS = {"train": 0.8, "validation": 0.1, "test": 0.1}
_GROUP_FIELDS = ("project_id", "session_id", "source_group_id")
_SPLIT_ORDER = ("train", "validation", "test")


def _stable_key(values: Iterable[str]) -> str:
    payload = "\n".join(sorted(values)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _ratio_map(ratios: Mapping[str, float] | None) -> dict[str, float]:
    supplied = _DEFAULT_RATIOS if ratios is None else ratios
    if set(supplied) != SPLITS:
        raise DatasetValidationError("ratios must define exactly train, validation, and test")
    normalized: dict[str, float] = {}
    for split in sorted(SPLITS):
        value = supplied[split]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise DatasetValidationError(f"ratio for {split} must be a finite number")
        try:
            number = float(value)
        except (OverflowError, ValueError):
            raise DatasetValidationError(f"ratio for {split} must be a finite number") from None
        if not math.isfinite(number) or number <= 0:
            raise DatasetValidationError(f"ratio for {split} must be finite and greater than zero")
        normalized[split] = number
    total = sum(normalized.values())
    if not math.isfinite(total) or total <= 0:
        raise DatasetValidationError("ratio total must be finite and greater than zero")
    return {split: value / total for split, value in normalized.items()}


def assign_splits(
    records: Iterable[Mapping[str, Any]],
    ratios: Mapping[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Return copied legacy-manifest records with deterministic split assignments.

    Records sharing a voicebank_id, source_id, provenance.source_reference, or
    any populated provenance project_id/session_id/source_group_id are joined
    into a single connected group. A group cannot cross splits. The input is
    not mutated. Existing split values are replaced; use only for fresh data.
    If at least three independent groups exist, each split receives one group
    before remaining groups are allocated by target-size deficit.
    """
    ratio_map = _ratio_map(ratios)
    copied: list[dict[str, Any]] = []
    for index, raw in enumerate(records, start=1):
        if not isinstance(raw, Mapping):
            raise DatasetValidationError(f"record {index} must be an object")
        record = dict(raw)
        record["split"] = "train"
        validate_record(record, index)
        copied.append(record)
    if not copied:
        raise DatasetValidationError("dataset manifest contains no records")

    ids: set[str] = set()
    for record in copied:
        record_id = record["record_id"]
        if record_id in ids:
            raise DatasetValidationError(f"duplicate record_id {record_id!r}")
        ids.add(record_id)

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

    owner: dict[tuple[str, str], int] = {}
    for index, record in enumerate(copied):
        provenance = record["provenance"]
        identities = [
            ("voicebank", record["voicebank_id"]),
            ("source", record["source_id"]),
        ]
        for field in ("source_reference", *_GROUP_FIELDS):
            value = provenance.get(field)
            if isinstance(value, str) and value.strip():
                identities.append((field, value.strip()))
        for identity in identities:
            if identity in owner:
                union(index, owner[identity])
            else:
                owner[identity] = index

    components: dict[int, list[int]] = defaultdict(list)
    for index in range(len(copied)):
        components[find(index)].append(index)

    groups = []
    for indices in components.values():
        tokens = []
        for index in indices:
            record = copied[index]
            tokens.extend((
                f"voicebank:{record['voicebank_id']}",
                f"source:{record['source_id']}",
            ))
            for field in ("source_reference", *_GROUP_FIELDS):
                value = record["provenance"].get(field)
                if isinstance(value, str) and value.strip():
                    tokens.append(f"{field}:{value.strip()}")
        groups.append((indices, _stable_key(tokens)))
    groups.sort(key=lambda item: (-len(item[0]), item[1]))

    target_counts = {split: len(copied) * ratio_map[split] for split in SPLITS}
    assigned_counts = {split: 0 for split in SPLITS}
    # Avoid accidentally leaving a split empty merely because its target is
    # smaller than the deficits of the larger splits. Leakage groups stay
    # indivisible; if fewer than three groups exist, some splits must be empty.
    reserved = min(len(groups), len(_SPLIT_ORDER))
    for index, (indices, _) in enumerate(groups[:reserved]):
        split = _SPLIT_ORDER[index]
        for record_index in indices:
            copied[record_index]["split"] = split
        assigned_counts[split] += len(indices)

    for indices, _ in groups[reserved:]:
        split = max(
            _SPLIT_ORDER,
            key=lambda name: (
                target_counts[name] - assigned_counts[name],
                -_SPLIT_ORDER.index(name),
            ),
        )
        for index in indices:
            copied[index]["split"] = split
        assigned_counts[split] += len(indices)

    validate_records(copied)
    return copied
