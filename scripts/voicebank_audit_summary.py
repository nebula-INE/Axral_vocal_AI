"""Aggregate per-voicebank audit JSON without exposing local paths or aliases."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import math
import re
from typing import Iterable


REQUIRED_AUDIT_COUNTERS = {"errors", "warnings"}
ALLOWED_AUDIT_COUNTERS = frozenset({
    "oto_files", "prefix_map_files", "oto_entries", "unique_aliases",
    "duplicate_alias_groups", "prefix_map_entries", "wav_files_checked",
    "wav_files_invalid", "wav_files_with_signal_issues", "wav_files_digital_silence",
    "wav_files_near_silence", "wav_files_clipping_suspected", "errors", "warnings",
})
ALLOWED_SPLITS = frozenset({"train", "validation", "test"})
ALLOWED_LABEL_USAGE = frozenset({
    "labels_seen", "labels_used", "labels_without_voiced_note"
})


def build_public_download_summary(summary: dict[str, object]) -> dict[str, object]:
    """Create an artifact-safe download summary without paths or unbounded Hub text."""
    allowed_statuses = {
        "completed", "completed_with_archive_errors", "no_voicebank_roots_found"
    }
    allowed_archive_statuses = {"extracted", "failed", "skipped"}

    archive_rows = summary.get("archive_results", [])
    status_counts: Counter[str] = Counter()
    error_counts: Counter[str] = Counter()
    if isinstance(archive_rows, list):
        for row in archive_rows:
            if not isinstance(row, dict):
                continue
            status = row.get("status")
            if isinstance(status, str) and status in allowed_archive_statuses:
                status_counts[status] += 1
            error_code = row.get("error_code")
            if (
                isinstance(error_code, str)
                and re.fullmatch(r"[a-z0-9_]{1,80}", error_code)
            ):
                error_counts[error_code] += 1

    license_documents = summary.get("license_documents", [])
    license_count = len(license_documents) if isinstance(license_documents, list) else 0

    def safe_nonnegative_int(key: str) -> int:
        value = summary.get(key, 0)
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0

    def safe_dataset_id() -> str | None:
        value = summary.get("dataset")
        if not isinstance(value, str):
            return None
        pattern = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}"
        return value if re.fullmatch(pattern, value) else None

    def safe_requested_revision() -> str | None:
        value = summary.get("requested_revision")
        if not isinstance(value, str) or len(value) > 128:
            return None
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}", value):
            return None
        if any(part in {".", ".."} for part in value.split("/")):
            return None
        return value

    def safe_license_identifier() -> str | None:
        value = summary.get("dataset_card_license")
        if not isinstance(value, str) or len(value) > 128:
            return None
        return value if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+_-]{0,127}", value) else None

    revision = summary.get("resolved_revision")
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", revision):
        revision = None

    status = summary.get("status")
    if not isinstance(status, str) or status not in allowed_statuses:
        status = None

    return {
        "schema_version": 1,
        "dataset": safe_dataset_id(),
        "requested_revision": safe_requested_revision(),
        "resolved_revision": revision.lower() if isinstance(revision, str) else None,
        "dataset_card_license": safe_license_identifier(),
        "license_documents_indexed": license_count,
        "selected_files": safe_nonnegative_int("selected_files"),
        "download_bytes": safe_nonnegative_int("download_bytes"),
        "archives_found": safe_nonnegative_int("archives_found"),
        "archive_status_counts": dict(sorted(status_counts.items())),
        "archive_error_code_counts": dict(sorted(error_counts.items())),
        "extracted_bytes": safe_nonnegative_int("extracted_bytes"),
        "voicebank_roots": safe_nonnegative_int("voicebank_roots"),
        "status": status,
    }


def build_public_model_report(report: dict[str, object]) -> dict[str, object]:
    """Project a private trainer report to a fixed, path-free metrics schema."""
    validation = report.get("manifest_validation")
    validation = validation if isinstance(validation, dict) else {}
    raw_split_counts = validation.get("records_by_split")
    split_counts = raw_split_counts if isinstance(raw_split_counts, dict) else {}

    def safe_count(value: object) -> int:
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0

    def safe_split_counts(value: object) -> dict[str, int]:
        if not isinstance(value, dict):
            return {}
        return {split: safe_count(value.get(split)) for split in sorted(ALLOWED_SPLITS)}

    def safe_split_metrics(value: object) -> dict[str, float]:
        if not isinstance(value, dict):
            return {}
        result: dict[str, float] = {}
        for split in sorted(ALLOWED_SPLITS):
            item = value.get(split)
            if isinstance(item, (int, float)) and not isinstance(item, bool):
                try:
                    if math.isfinite(item):
                        result[split] = float(item)
                except (OverflowError, TypeError, ValueError):
                    continue
        return result

    def safe_evaluation_metrics(value: object) -> dict[str, float]:
        if not isinstance(value, dict):
            return {}
        allowed = {"mae_semitones", "zero_delta_baseline_mae_semitones"}
        result: dict[str, float] = {}
        for key in allowed:
            item = value.get(key)
            if isinstance(item, (int, float)) and not isinstance(item, bool):
                try:
                    if math.isfinite(item):
                        result[key] = float(item)
                except (OverflowError, TypeError, ValueError):
                    continue
        return result

    raw_usage = report.get("label_usage")
    label_usage = {
        key: safe_count(raw_usage.get(key))
        for key in sorted(ALLOWED_LABEL_USAGE)
    } if isinstance(raw_usage, dict) else {}
    raw_examples = report.get("usable_examples_by_split")
    examples = safe_split_counts(raw_examples)

    model = report.get("model")
    public_model: dict[str, object] = {}
    if isinstance(model, dict):
        for key in (
            "model_type", "schema_version", "feature_version",
            "feature_names", "target_kind", "weights", "safety",
        ):
            value = model.get(key)
            if key == "feature_names" and isinstance(value, list):
                public_model[key] = [
                    item for item in value
                    if isinstance(item, str) and re.fullmatch(r"[a-z0-9_]{1,80}", item)
                ][:32]
            elif key == "weights" and isinstance(value, list):
                weights: list[float] = []
                for item in value[:32]:
                    if isinstance(item, (int, float)) and not isinstance(item, bool):
                        try:
                            if math.isfinite(item):
                                weights.append(float(item))
                        except (OverflowError, TypeError, ValueError):
                            continue
                public_model[key] = weights
            elif key == "safety" and isinstance(value, dict):
                public_model[key] = {
                    name: flag for name, flag in value.items()
                    if name in {
                        "proposal_only", "waveform_generation",
                        "production_renderer_integration",
                    } and isinstance(flag, bool)
                }
            elif key == "model_type":
                if value == "linear_ridge_pitch_delta":
                    public_model[key] = value
            elif key == "target_kind":
                if value == "pitch_delta_semitones":
                    public_model[key] = value
            elif key in {"schema_version", "feature_version"}:
                if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100:
                    public_model[key] = value

    return {
        "schema_version": 1,
        "status": (
            "experimental_training_complete"
            if report.get("status") == "experimental_training_complete"
            else "unknown"
        ),
        "test_evaluation_included": report.get("test_evaluation_included") is True,
        "manifest_validation": {
            "status": "valid" if validation.get("status") == "valid" else "unknown",
            "records": safe_count(validation.get("records")),
            "labeled_records": safe_count(validation.get("labeled_records")),
            "records_by_split": safe_split_counts(split_counts),
            "require_labeled": validation.get("require_labeled") is True,
        },
        "label_usage": label_usage,
        "usable_examples_by_split": examples,
        "mae_semitones": safe_split_metrics(report.get("mae_semitones")),
        "zero_delta_baseline_mae_semitones": safe_split_metrics(
            report.get("zero_delta_baseline_mae_semitones")
        ),
        "evaluation_by_split": {
            split: safe_evaluation_metrics(metrics)
            for split, metrics in report.get("evaluation_by_split", {}).items()
            if split in ALLOWED_SPLITS and isinstance(metrics, dict)
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
    aggregate_issue_codes: Counter[str] = Counter()

    for bank_index, report_path, exit_code in results:
        counts: dict[str, int] = {}
        bank_issue_codes: Counter[str] = Counter()
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
                if key in ALLOWED_AUDIT_COUNTERS
                and isinstance(value, int)
                and not isinstance(value, bool)
                and value >= 0
            }
            raw_issues = report.get("issues", []) if isinstance(report, dict) else []
            if isinstance(raw_issues, list):
                for issue in raw_issues:
                    if not isinstance(issue, dict):
                        continue
                    severity = issue.get("severity")
                    code = issue.get("code")
                    if (
                        severity in {"error", "warning"}
                        and isinstance(code, str)
                        and re.fullmatch(r"[a-z0-9_]{1,80}", code)
                    ):
                        bank_issue_codes[f"{severity}:{code}"] += 1
            report_status = "completed"
            aggregate.update(counts)
            aggregate_issue_codes.update(bank_issue_codes)
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
            "issue_code_counts": dict(sorted(bank_issue_codes.items())),
        })

    return {
        "schema_version": 1,
        "voicebank_roots": len(banks),
        "audits_completed": sum(
            bank["status"] in {"completed", "completed_with_findings"}
            for bank in banks
        ),
        "aggregate": dict(sorted(aggregate.items())),
        "issue_code_counts": dict(sorted(aggregate_issue_codes.items())),
        "failures": failures,
        "banks": banks,
    }
