#!/usr/bin/env python3
"""Audit metadata and pitch-label coverage without opening audio."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from axral_vocal_ai.dataset_audit import audit_dataset
from axral_vocal_ai.training_data import DatasetValidationError, validate_jsonl


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="metadata-only JSONL manifest")
    parser.add_argument("--output", type=Path, help="optional JSON report path")
    args = parser.parse_args()

    try:
        validation = validate_jsonl(args.manifest, require_labeled=True)
        with args.manifest.open("r", encoding="utf-8") as stream:
            records = [
                json.loads(line)
                for line in stream
                if line.strip() and not line.lstrip().startswith("#")
            ]
        report = audit_dataset(records)
        report["manifest_validation"] = validation
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
