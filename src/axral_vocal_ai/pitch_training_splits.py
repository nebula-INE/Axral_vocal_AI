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
    """Return copied records with deterministic, leakage-safe split assignments.

    Records use the legacy training_data.py manifest schema. All records sharing
    a voicebank_id, source_id, or provenance.source_reference are joined into a
    single connected group; connected groups can never cross splits. The input
    records are not mutated. Existing split values are deliberately ignored and
    replaced, so callers should only use this for a fresh unsplit manifest.
    """
    ratio_map = _ratio_map(ratios)
    copied: list[dict[str, Any]] = []
    for index, raw in enumerate(records, start=1):
        if not isinstance(raw, Mapping):
            raise DatasetValidationError(f"record {index} must be an object")
        record = dict(raw)
        record["split"] = "train"  # validate legacy schema before assigning groups
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

    # Union-find over records. Sharing any protected identity joins the groups.
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
        identities = [
            ("voicebank", record["voicebank_id"]),
            ("source", record["source_id"]),
        ]
        provenance = record["provenance"]
        reference = provenance.get("source_reference")
        if isinstance(reference, str) and reference.strip():
            identities.append(("source_reference", reference))
        for identity in identities:
            if identity in owner:
                union(index, owner[identity])
            else:
                owner[identity] = index

    components: dict[int, list[int]] = defaultdict(list)
    for index in range(len(copied)):
        components[find(index)].append(index)

    # Largest groups first for better balance; stable hashes break ties without
    # depending on input order, process hash randomization, or wall-clock time.
    groups = []
    for indices in components.values():
        tokens = []
        for index in indices:
            record = copied[index]
            tokens.extend((
                f"voicebank:{record['voicebank_id']}",
                f"source:{record['source_id']}",
            ))
            source_reference = record["provenance"].get("source_reference")
            if isinstance(source_reference, str) and source_reference.strip():
                tokens.append(f"source_reference:{source_reference}")
        groups.append((indices, _stable_key(tokens)))
    groups.sort(key=lambda item: (-len(item[0]), item[1]))

    target_counts = {split: len(copied) * ratio_map[split] for split in SPLITS}
    assigned_counts = {split: 0 for split in SPLITS}
    split_order = ("train", "validation", "test")
    for indices, _ in groups:
        # Put each indivisible group where it most reduces the current target
        # deficit. Fixed split order resolves exact ties deterministically.
        split = max(
            split_order,
            key=lambda name: (target_counts[name] - assigned_counts[name], -split_order.index(name)),
        )
        for index in indices:
            copied[index]["split"] = split
        assigned_counts[split] += len(indices)

    # Reuse the existing full-manifest validator as the final leakage and schema
    # gate. Do not claim training readiness unless the caller requests it there.
    validate_records(copied)
    return copied
