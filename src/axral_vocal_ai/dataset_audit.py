"""Metadata-only readiness diagnostics for experimental pitch-delta datasets.

This module never opens audio or makes a claim about perceptual singing quality.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Any, Iterable

from .pitch_model import TrainingExample, examples_from_records

SPLITS = ("train", "validation", "test")
PITCH_RANGES = (
    ("midi_0_47", 0.0, 48.0),
    ("midi_48_59", 48.0, 60.0),
    ("midi_60_71", 60.0, 72.0),
    ("midi_72_83", 72.0, 84.0),
    ("midi_84_127", 84.0, 128.0),
)


def _label_stats(rows: list[TrainingExample]) -> dict[str, Any]:
    values = [row.target for row in rows]
    if not values:
        return {
            "usable_labels": 0,
            "mean_delta_semitones": None,
            "median_delta_semitones": None,
            "min_delta_semitones": None,
            "max_delta_semitones": None,
            "zero_delta_labels": 0,
            "nonzero_delta_labels": 0,
        }
    return {
        "usable_labels": len(values),
        "mean_delta_semitones": sum(values) / len(values),
        "median_delta_semitones": median(values),
        "min_delta_semitones": min(values),
        "max_delta_semitones": max(values),
        "zero_delta_labels": sum(value == 0.0 for value in values),
        "nonzero_delta_labels": sum(value != 0.0 for value in values),
    }


def audit_dataset(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Summarize label coverage and distribution after manifest validation.

    Callers should validate permissions, provenance, schema, and split isolation
    with training_data.validate_records/validate_jsonl before using this report.
    """
    materialized = list(records)
    examples, usage = examples_from_records(materialized)
    raw_labels_by_split = {split: 0 for split in SPLITS}
    records_by_split = {split: 0 for split in SPLITS}
    for record in materialized:
        split = record["split"]
        records_by_split[split] += 1
        target = record.get("target")
        if isinstance(target, dict):
            raw_labels_by_split[split] += len(target.get("points", []))

    usable_by_split: dict[str, list[TrainingExample]] = {
        split: [row for row in examples if row.split == split] for split in SPLITS
    }
    by_voicebank: dict[str, list[TrainingExample]] = defaultdict(list)
    by_range: dict[str, list[TrainingExample]] = defaultdict(list)
    for row in examples:
        by_voicebank[row.voicebank_id].append(row)
        midi = row.features[1] * 127.0
        for name, lower, upper in PITCH_RANGES:
            if lower <= midi < upper:
                by_range[name].append(row)
                break

    split_reports: dict[str, Any] = {}
    for split in SPLITS:
        raw_count = raw_labels_by_split[split]
        usable_count = len(usable_by_split[split])
        split_reports[split] = {
            "records": records_by_split[split],
            "raw_labels": raw_count,
            **_label_stats(usable_by_split[split]),
            "label_coverage_ratio": usable_count / raw_count if raw_count else None,
        }

    return {
        "status": "audited",
        "records": len(materialized),
        "raw_labels": sum(raw_labels_by_split.values()),
        "usable_labels": len(examples),
        "label_coverage_ratio": (
            len(examples) / sum(raw_labels_by_split.values())
            if sum(raw_labels_by_split.values()) else None
        ),
        "label_usage": usage,
        "by_split": split_reports,
        "by_voicebank": {
            bank: _label_stats(rows) | {
                "split": rows[0].split,
                "records_with_usable_labels": len({row.record_id for row in rows}),
            }
            for bank, rows in sorted(by_voicebank.items())
        },
        "by_midi_range": {
            name: _label_stats(by_range.get(name, []))
            for name, _, _ in PITCH_RANGES
        },
        "limitations": [
            "This report uses metadata and labels only; it does not load audio.",
            "Coverage means labels mapped to an unambiguous voiced note, not label correctness.",
            "Label distributions and counts do not establish perceptual naturalness or generalization.",
            "Review permissions, label quality, and held-out voicebank results independently.",
        ],
    }
