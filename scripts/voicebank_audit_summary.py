"""Aggregate per-voicebank audit JSON without exposing local paths or aliases."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Iterable


REQUIRED_AUDIT_COUNTERS = {"errors", "warnings"}


def build_public_download_summary(summary: dict[str, object]) -> dict[str, object]:
    """Create an artifact-safe download summary without dataset file paths."""
    archive_rows = summary.get("archive_results", [])
    status_counts: Counter[str] = Counter()
    error_counts: Counter[str] = Counter()
    if isinstance(archive_rows, list):
        for row in archive_rows:
            if not isinstance(row, dict):
                continue
            status = row.get("status")
            if isinstance(status, str):
                status_counts[status] += 1
            error_code = row.get("error_code")
            if isinstance(error_code, str) and error_code:
                error_counts[error_code] += 1

    license_documents = summary.get("license_documents", [])
    license_count = len(license_documents) if isinstance(license_documents, list) else 0

    def safe_nonnegative_int(key: str) -> int:
        value = summary.get(key, 0)
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0

    def safe_optional_text(key: str) -> str | None:
        value = summary.get(key)
        return value if isinstance(value, str) and value else None

    return {
        "schema_version": 1,
        "dataset": safe_optional_text("dataset"),
        "requested_revision": safe_optional_text("requested_revision"),
        "resolved_revision": safe_optional_text("resolved_revision"),
        "dataset_card_license": safe_optional_text("dataset_card_license"),
        "license_documents_indexed": license_count,
        "selected_files": safe_nonnegative_int("selected_files"),
        "download_bytes": safe_nonnegative_int("download_bytes"),
        "archives_found": safe_nonnegative_int("archives_found"),
        "archive_status_counts": dict(sorted(status_counts.items())),
        "archive_error_code_counts": dict(sorted(error_counts.items())),
        "extracted_bytes": safe_nonnegative_int("extracted_bytes"),
        "voicebank_roots": safe_nonnegative_int("voicebank_roots"),
        "status": safe_optional_text("status"),
    }


def build_public_model_report(report: dict[str, object]) -> dict[str, object]:
    """Project a private trainer report to metrics/weights without bank IDs."""
    validation = report.get("manifest_validation")
    validation = validation if isinstance(validation, dict) else {}
    raw_split_counts = validation.get("records_by_split")
    split_counts = raw_split_counts if isinstance(raw_split_counts, dict) else {}

    def safe_count(value: object) -> int:
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0

    def safe_metrics(value: object) -> dict[str, object]:
        if not isinstance(value, dict):
            return {}
        result: dict[str, object] = {}
        for key, item in value.items():
            if isinstance(key, str) and (
                item is None
                or (isinstance(item, (int, float)) and not isinstance(item, bool))
            ):
                result[key] = item
        return result

    raw_usage = report.get("label_usage")
    label_usage = {
        key: safe_count(value)
        for key, value in raw_usage.items()
        if isinstance(key, str)
    } if isinstance(raw_usage, dict) else {}
    raw_examples = report.get("usable_examples_by_split")
    examples = {
        key: safe_count(value)
        for key, value in raw_examples.items()
        if isinstance(key, str)
    } if isinstance(raw_examples, dict) else {}

    model = report.get("model")
    public_model: dict[str, object] = {}
    if isinstance(model, dict):
        for key in (
            "model_type", "schema_version", "feature_version",
            "feature_names", "target_kind", "weights", "safety",
        ):
            value = model.get(key)
            if key in {"feature_names", "weights"} and isinstance(value, list):
                public_model[key] = value
            elif key == "safety" and isinstance(value, dict):
                public_model[key] = {
                    name: flag for name, flag in value.items()
                    if isinstance(name, str) and isinstance(flag, bool)
                }
            elif key not in {"feature_names", "weights", "safety"} and isinstance(value, (str, int)) and not isinstance(value, bool):
                public_model[key] = value

    return {
        "schema_version": 1,
        "status": report.get("status") if isinstance(report.get("status"), str) else "unknown",
        "test_evaluation_included": report.get("test_evaluation_included") is True,
        "manifest_validation": {
            "status": validation.get("status") if isinstance(validation.get("status"), str) else "unknown",
            "records": safe_count(validation.get("records")),
            "labeled_records": safe_count(validation.get("labeled_records")),
            "records_by_split": {
                split: safe_count(split_counts.get(split))
                for split in ("train", "validation", "test")
            },
            "require_labeled": validation.get("require_labeled") is True,
        },
        "label_usage": label_usage,
        "usable_examples_by_split": examples,
        "mae_semitones": safe_metrics(report.get("mae_semitones")),
        "zero_delta_baseline_mae_semitones": safe_metrics(
            report.get("zero_delta_baseline_mae_semitones")
        ),
        "evaluation_by_split": {
            split: safe_metrics(metrics)
            for split, metrics in report.get("evaluation_by_split", {}).items()
            if isinstance(split, str)
        } if isinstance(report.get("evaluation_by_split"), dict) else {},
        "model": public_model,
        "limitations": [
            "Metadata-only regression MVP; no waveform synthesis.",
            "Metrics do not establish singing naturalness or generalization.",
            "Review data rights and labels independently.",
            "Do not integrate into the production renderer without a separate reviewed gate.",
        ],
    }


def build_audit_index(
    results: Iterable[tuple[int, Path, int]],
) -> dict[str, object]:
    """Build a compact index from (bank index, report path, CLI exit code) rows.

    A bank is a training-gate failure when its CLI exits nonzero, its report is
    missing/invalid, or its report explicitly contains errors. The exit code
    alone is not trusted as proof that a valid audit report was produced.
    """
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
            for key in REQUIRED_AUDIT_COUNTERS:
                value = raw_summary.get(key)
                if (
                    isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < 0
                ):
                    raise ValueError("audit_required_counter_invalid")
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

        failure_code = None
        if report_status != "completed":
            failure_code = "invalid_or_missing_audit_report"
        elif exit_code != 0:
            failure_code = "audit_cli_nonzero_exit"
        elif counts.get("errors", 0) > 0:
            failure_code = "audit_report_contains_errors"

        if failure_code is not None:
            failures.append({
                "bank_index": bank_index,
                "exit_code": exit_code,
                "error_count": counts.get("errors", 0),
                "error_code": failure_code,
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
