"""Aggregate per-voicebank audit JSON without exposing local paths or aliases."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Iterable


def build_audit_index(
    results: Iterable[tuple[int, Path, int]],
) -> dict[str, object]:
    """Build a compact index from (bank index, report path, CLI exit code) rows."""
    banks: list[dict[str, object]] = []
    failures: list[dict[str, int | str]] = []
    aggregate: Counter[str] = Counter()

    for bank_index, report_path, exit_code in results:
        counts: dict[str, int] = {}
        report_status = "missing"
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            raw_summary = report.get("summary") if isinstance(report, dict) else None
            if not isinstance(raw_summary, dict):
                raise ValueError("audit_summary_missing")
            counts = {
                key: value
                for key, value in raw_summary.items()
                if isinstance(key, str)
                and isinstance(value, int)
                and not isinstance(value, bool)
                and value >= 0
            }
            report_status = "completed"
            aggregate.update(counts)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            report_status = "invalid_or_missing_report"

        if exit_code != 0:
            failures.append({
                "bank_index": bank_index,
                "exit_code": exit_code,
                "error_count": counts.get("errors", 0),
            })
            if report_status == "completed":
                report_status = "completed_with_findings"
        banks.append({
            "bank_index": bank_index,
            "status": report_status,
            "summary": counts,
        })

    return {
        "schema_version": 1,
        "voicebank_roots": len(banks),
        "audits_completed": sum(
            bank["status"] in {"completed", "completed_with_findings"}
            for bank in banks
        ),
        "aggregate": dict(sorted(aggregate.items())),
        "failures": failures,
        "banks": banks,
    }
