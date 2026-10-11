"""CLI for validating an Axral Vocal AI metadata-only JSONL manifest."""
from __future__ import annotations

import argparse
import json
import sys

from axral_vocal_ai.training_data import DatasetValidationError, validate_jsonl


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", help="Path to a JSONL metadata manifest")
    parser.add_argument(
        "--require-labeled",
        action="store_true",
        help="Require pitch-delta labels on every record (training-readiness gate)",
    )
    args = parser.parse_args()
    try:
        summary = validate_jsonl(args.manifest, require_labeled=args.require_labeled)
    except DatasetValidationError as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
