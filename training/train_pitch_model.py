#!/usr/bin/env python3
"""Train and evaluate the experimental metadata-only pitch-delta model."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

# Running this file directly adds training/ rather than the repository root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from axral_vocal_ai.pitch_model import (
    examples_from_records,
    compare_with_zero_baseline,
    fit_ridge,
)
from axral_vocal_ai.training_data import DatasetValidationError, validate_jsonl


def assess_validation(evaluation: dict[str, dict[str, float | None]]) -> tuple[str, list[str]]:
    """Summarize validation performance without treating training completion as quality."""
    metrics = evaluation.get("validation")
    if not metrics:
        return "unavailable", ["Validation metrics are unavailable; do not use this model."]

    improvement = metrics.get("mae_improvement_over_zero_baseline_semitones")
    if (
        isinstance(improvement, bool)
        or not isinstance(improvement, (int, float))
        or not math.isfinite(improvement)
    ):
        return "unavailable", [
            "Validation baseline comparison is missing or non-finite; do not use this model."
        ]
    if improvement > 0:
        return "better_than_zero_baseline", []
    if improvement < 0:
        return "worse_than_zero_baseline", [
            "Validation MAE is worse than the zero-delta baseline; do not use this model without investigating."
        ]
    return "equal_to_zero_baseline", [
        "Validation MAE does not improve on the zero-delta baseline; there is no demonstrated benefit."
    ]


def build_label_quality_report(records, counts, examples):
    """Report label coverage and skipped-label rates by split and voicebank.

    This is a metadata/label alignment diagnostic, not a judgment that labels
    are acoustically correct. It deliberately reports counts as well as rates.
    """
    groups = {}
    for record in records:
        bank = record["voicebank_id"]
        split = record["split"]
        key = (split, bank)
        item = groups.setdefault(key, {"records": 0, "labels_seen": 0, "labels_used": 0})
        item["records"] += 1
        target = record.get("target")
        if isinstance(target, dict) and isinstance(target.get("points"), list):
            item["labels_seen"] += len(target["points"])
    for example in examples:
        groups[(example.split, example.voicebank_id)]["labels_used"] += 1

    by_split = {}
    by_voicebank = {}
    for (split, bank), item in sorted(groups.items()):
        item["labels_without_voiced_note"] = item["labels_seen"] - item["labels_used"]
        item["label_use_rate"] = (
            item["labels_used"] / item["labels_seen"] if item["labels_seen"] else None
        )
        by_split.setdefault(split, {"records": 0, "labels_seen": 0, "labels_used": 0})
        for field in ("records", "labels_seen", "labels_used"):
            by_split[split][field] += item[field]
        by_voicebank.setdefault(bank, {})[split] = item
    for item in by_split.values():
        item["labels_without_voiced_note"] = item["labels_seen"] - item["labels_used"]
        item["label_use_rate"] = (
            item["labels_used"] / item["labels_seen"] if item["labels_seen"] else None
        )
    seen = counts["labels_seen"]
    used = counts["labels_used"]
    return {
        "definition": "label_use_rate is the share of target points mapped to a usable note; it does not measure acoustic correctness",
        "overall": {
            **counts,
            "label_use_rate": used / seen if seen else None,
            "label_skip_rate": counts["labels_without_voiced_note"] / seen if seen else None,
        },
        "by_split": by_split,
        "by_voicebank": by_voicebank,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="metadata-only JSONL manifest")
    parser.add_argument("--output", type=Path, default=Path("pitch_delta_model.json"))
    parser.add_argument("--alpha", type=float, default=1.0, help="ridge regularization strength (default: 1.0)")
    parser.add_argument(
        "--evaluate-test",
        action="store_true",
        help="evaluate the held-out test split once model/settings are finalized",
    )
    args = parser.parse_args()

    try:
        summary = validate_jsonl(args.manifest, require_labeled=True)
        with args.manifest.open("r", encoding="utf-8") as stream:
            records = [json.loads(line) for line in stream if line.strip() and not line.lstrip().startswith("#")]
        examples, counts = examples_from_records(records)
        by_split = {split: [row for row in examples if row.split == split]
                    for split in ("train", "validation", "test")}
        if not by_split["train"]:
            raise ValueError("no usable voiced labels in train split")
        if not by_split["validation"] or not by_split["test"]:
            raise ValueError("validation and test splits must each contain usable voiced labels")

        # Fit only on training examples. By default, do not expose held-out test
        # metrics during model iteration; evaluating them repeatedly can leak
        # test-set information into model/settings decisions.
        model = fit_ridge(by_split["train"], alpha=args.alpha)
        evaluated_splits = ("train", "validation", "test") if args.evaluate_test else ("train", "validation")
        evaluation = {
            split: compare_with_zero_baseline(by_split[split], model)
            for split in evaluated_splits
        }
        model_mae = {split: metrics["mae_semitones"] for split, metrics in evaluation.items()}
        baseline_mae = {
            split: metrics["zero_delta_baseline_mae_semitones"]
            for split, metrics in evaluation.items()
        }
        validation_assessment, quality_warnings = assess_validation(evaluation)
        label_quality = build_label_quality_report(records, counts, examples)
        report = {
            "status": "experimental_training_complete",
            "validation_assessment": validation_assessment,
            "quality_warnings": quality_warnings,
            "test_evaluation_included": args.evaluate_test,
            "manifest_validation": summary,
            "label_usage": counts,
            "label_quality": label_quality,
            "usable_examples_by_split": {split: len(rows) for split, rows in by_split.items()},
            "mae_semitones": model_mae,
            "zero_delta_baseline_mae_semitones": baseline_mae,
            "evaluation_by_split": evaluation,
            "model": model.to_dict(),
            "limitations": [
                "Metadata-only regression MVP; no waveform synthesis.",
                "Compare validation MAE against the zero-delta baseline during iteration; negative improvement means this model is worse.",
                "Held-out test metrics are omitted unless --evaluate-test is explicitly supplied after model/settings decisions are finalized.",
                "Metrics on small datasets are not evidence of naturalness or generalization.",
                "Review data rights and labels independently; manifest approval is not legal verification.",
                "Do not integrate into the production renderer without a separate reviewed gate.",
            ],
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps({
            "status": report["status"],
            "validation_assessment": report["validation_assessment"],
            "quality_warnings": report["quality_warnings"],
            "test_evaluation_included": report["test_evaluation_included"],
            "label_usage": counts,
            "label_quality": report["label_quality"],
            "usable_examples_by_split": report["usable_examples_by_split"],
            "mae_semitones": model_mae,
            "zero_delta_baseline_mae_semitones": baseline_mae,
            "evaluation_by_split": report["evaluation_by_split"],
        }, indent=2))
        print(f"Model report written to: {args.output}")
        return 0
    except (DatasetValidationError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"training failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
