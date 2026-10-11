#!/usr/bin/env python3
"""Train and evaluate the experimental metadata-only pitch-delta model."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Running this file directly adds training/ rather than the repository root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from axral_vocal_ai.pitch_model import (
    examples_from_records,
    fit_ridge,
    mean_absolute_error,
    zero_baseline_mae,
)
from axral_vocal_ai.training_data import DatasetValidationError, validate_jsonl


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="metadata-only JSONL manifest")
    parser.add_argument("--output", type=Path, default=Path("pitch_delta_model.json"))
    parser.add_argument("--alpha", type=float, default=1.0, help="ridge regularization strength (default: 1.0)")
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
        model = fit_ridge(by_split["train"], alpha=args.alpha)
        model_mae = {
            split: mean_absolute_error(rows, model)
            for split, rows in by_split.items()
        }
        baseline_mae = {
            split: zero_baseline_mae(rows)
            for split, rows in by_split.items()
        }
        report = {
            "status": "experimental_training_complete",
            "manifest_validation": summary,
            "label_usage": counts,
            "usable_examples_by_split": {split: len(rows) for split, rows in by_split.items()},
            "mae_semitones": model_mae,
            "zero_delta_baseline_mae_semitones": baseline_mae,
            "mae_improvement_over_zero_baseline_semitones": {
                split: baseline_mae[split] - model_mae[split]
                for split in by_split
            },
            "model": model.to_dict(),
            "limitations": [
                "Metadata-only regression MVP; no waveform synthesis.",
                "Compare validation/test MAE against the zero-delta baseline; negative improvement means this model is worse.",
                "Metrics on small datasets are not evidence of naturalness or generalization.",
                "Review data rights and labels independently; manifest approval is not legal verification.",
                "Do not integrate into the production renderer without a separate reviewed gate.",
            ],
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps({
            "status": report["status"],
            "label_usage": counts,
            "usable_examples_by_split": report["usable_examples_by_split"],
            "mae_semitones": model_mae,
            "zero_delta_baseline_mae_semitones": baseline_mae,
            "mae_improvement_over_zero_baseline_semitones": report["mae_improvement_over_zero_baseline_semitones"],
        }, indent=2))
        print(f"Model report written to: {args.output}")
        return 0
    except (DatasetValidationError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"training failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
