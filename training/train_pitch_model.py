#!/usr/bin/env python3
"""Train and evaluate the experimental metadata-only pitch-delta model."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

import numpy as np

# Running this file directly adds training/ rather than the repository root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _source_revision() -> str | None:
    """Return an explicitly supplied or locally discoverable source revision."""
    supplied = os.environ.get("AXRAL_SOURCE_REVISION") or os.environ.get("GITHUB_SHA")
    if supplied and supplied.strip():
        return supplied.strip()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
            text=True, check=True, timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    revision = result.stdout.strip()
    return revision or None

from axral_vocal_ai.pitch_model import (
    FEATURE_VERSION,
    examples_from_records,
    compare_with_zero_baseline,
    fit_ridge,
)
from axral_vocal_ai.training_data import DatasetValidationError, validate_jsonl


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
        report = {
            "status": "experimental_training_complete",
            "run_metadata": {
                "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                "source_revision": _source_revision(),
                "python_version": platform.python_version(),
                "numpy_version": np.__version__,
                "feature_version": FEATURE_VERSION,
                "alpha": args.alpha,
                "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
            },
            "test_evaluation_included": args.evaluate_test,
            "manifest_validation": summary,
            "label_usage": counts,
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
            "run_metadata": report["run_metadata"],
            "test_evaluation_included": report["test_evaluation_included"],
            "label_usage": counts,
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
