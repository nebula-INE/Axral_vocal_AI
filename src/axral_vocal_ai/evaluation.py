"""Stratified metrics for experimental pitch-delta regression.

Evaluation is metadata-only and does not load audio or touch a renderer.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Iterable

from .pitch_model import (
    LinearPitchDeltaModel,
    TrainingExample,
    compare_with_zero_baseline,
)

PITCH_RANGES = (
    ("midi_0_47", 0.0, 48.0),
    ("midi_48_59", 48.0, 60.0),
    ("midi_60_71", 60.0, 72.0),
    ("midi_72_83", 72.0, 84.0),
    ("midi_84_127", 84.0, 128.0),
)


def _metrics(rows: list[TrainingExample], model: LinearPitchDeltaModel) -> dict[str, Any]:
    comparison = compare_with_zero_baseline(rows, model)
    if not rows:
        return {"examples": 0, **comparison, "rmse_semitones": None}
    squared_errors = [
        (model.predict_features(row.features) - row.target) ** 2
        for row in rows
    ]
    return {
        "examples": len(rows),
        **comparison,
        "rmse_semitones": math.sqrt(sum(squared_errors) / len(squared_errors)),
    }


def evaluate_stratified(
    examples: Iterable[TrainingExample],
    model: LinearPitchDeltaModel,
    *,
    split: str = "test",
) -> dict[str, Any]:
    """Report overall, per-voicebank, and per-MIDI-range metrics for one split."""
    if split not in {"train", "validation", "test"}:
        raise ValueError("split must be train, validation, or test")
    rows = list(examples)
    if any(row.split != split for row in rows):
        raise ValueError(f"all examples must belong to the requested {split!r} split")
    if not rows:
        raise ValueError(f"no usable labeled examples in {split!r} split")

    by_bank: dict[str, list[TrainingExample]] = defaultdict(list)
    by_range: dict[str, list[TrainingExample]] = defaultdict(list)
    for row in rows:
        by_bank[row.voicebank_id].append(row)
        midi = row.features[1] * 127.0
        for name, lower, upper in PITCH_RANGES:
            if lower <= midi < upper:
                by_range[name].append(row)
                break

    return {
        "status": "evaluated",
        "split": split,
        "examples": len(rows),
        "overall": _metrics(rows, model),
        "by_voicebank": {
            bank: _metrics(bank_rows, model)
            for bank, bank_rows in sorted(by_bank.items())
        },
        "by_midi_range": {
            name: _metrics(by_range.get(name, []), model)
            for name, _, _ in PITCH_RANGES
        },
        "interpretation": [
            "Positive MAE improvement means better than predicting zero delta; negative means worse.",
            "Per-bank and per-range results expose uneven performance hidden by aggregate metrics.",
            "Metrics do not measure perceptual naturalness and do not establish generalization from small samples.",
            "Do not repeatedly tune against held-out test results; use validation for model selection.",
        ],
    }
