"""Command-line entry point for reproducible UTAU voicebank audits.

Usage:
    python -m axral_vocal_ai.voicebank_audit_cli /path/to/voicebank
    python -m axral_vocal_ai.voicebank_audit_cli /path/to/voicebank --output audit.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from axral_vocal_ai.voicebank_analysis import analyze_voicebank


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit UTAU oto.ini, prefix.map, WAV structure, and PCM signal findings."
    )
    parser.add_argument("voicebank", type=Path, help="root directory of the voicebank to inspect")
    parser.add_argument(
        "--output", "-o", type=Path,
        help="write the JSON report to this file instead of standard output",
    )
    parser.add_argument(
        "--fail-on",
        choices=("never", "warning", "error"),
        default="error",
        help="exit with status 1 when findings at this severity or above exist (default: error)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        analysis = analyze_voicebank(args.voicebank)
    except (OSError, ValueError) as exc:
        print(f"voicebank audit failed: {exc}", file=sys.stderr)
        return 2

    report = analysis.to_json(indent=2)
    if args.output is None:
        print(report)
    else:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(report + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"could not write report: {exc}", file=sys.stderr)
            return 2

    if args.fail_on == "never":
        return 0
    if args.fail_on == "error" and analysis.summary["errors"] > 0:
        return 1
    if args.fail_on == "warning" and (
        analysis.summary["errors"] > 0 or analysis.summary["warnings"] > 0
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
