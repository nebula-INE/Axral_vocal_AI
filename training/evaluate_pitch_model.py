"""Evaluate a saved experimental pitch model on a validated metadata manifest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from axral_vocal_ai.evaluation import evaluate_stratified
from axral_vocal_ai.pitch_model import LinearPitchDeltaModel, examples_from_records
from axral_vocal_ai.training_data import DatasetValidationError, validate_jsonl


def _load_model(path: Path) -> LinearPitchDeltaModel:
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read model artifact: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("model artifact must contain a JSON object")
    if "model" in payload:
        if payload.get("status") != "experimental_training_complete":
            raise ValueError("training report status is missing or unsupported")
        payload = payload["model"]
    try:
        return LinearPitchDeltaModel.from_dict(payload)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid model artifact: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="validated metadata-only JSONL manifest")
    parser.add_argument("model", type=Path, help="model JSON or training report JSON")
    parser.add_argument("--split", choices=("validation", "test"), default="test",
                        help="split to evaluate; test is for final evaluation only")
    parser.add_argument("--output", type=Path, help="optional path for a JSON evaluation report")
    args = parser.parse_args()
    try:
        manifest_summary = validate_jsonl(args.manifest, require_labeled=True)
        with args.manifest.open("r", encoding="utf-8") as stream:
            records = [json.loads(line) for line in stream
                       if line.strip() and not line.lstrip().startswith("#")]
        examples, label_usage = examples_from_records(records)
        selected = [example for example in examples if example.split == args.split]
        model = _load_model(args.model)
        report = evaluate_stratified(selected, model, split=args.split)
        report["manifest_validation"] = manifest_summary
        report["label_usage"] = label_usage
        encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded, encoding="utf-8")
        print(encoded, end="")
        return 0
    except (DatasetValidationError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
