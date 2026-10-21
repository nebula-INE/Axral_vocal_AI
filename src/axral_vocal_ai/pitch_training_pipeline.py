"""End-to-end metadata-only dataset preparation for pitch training.

This orchestration layer keeps the two dataset schemas separate. It validates
and assigns leakage-safe splits, then builds an aggregate quality report. It
never reads audio, trains a model, repairs labels, or changes VO-SE_vocal.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from .pitch_training_quality import report_example_records, report_legacy_records
from .pitch_training_splits import assign_splits
from .pitch_training_contract_splits import assign_example_splits


def prepare_legacy_dataset(
    records: Iterable[Mapping[str, Any]],
    *,
    ratios: Mapping[str, float] | None = None,
    dataset_origin: str = "synthetic_fixture",
) -> dict[str, Any]:
    """Assign safe splits and report quality for legacy-manifest records.

    Raises DatasetValidationError for invalid records or split leakage that
    cannot be resolved by the deterministic assignment policy.
    """
    assigned = assign_splits(records, ratios=ratios)
    report = report_legacy_records(assigned, dataset_origin=dataset_origin)
    if report["records_invalid"]:
        raise ValueError(
            "legacy dataset failed post-split quality gate: "
            f"{report['records_invalid']} invalid records; "
            f"issues={report['validation_issue_counts']}"
        )
    return {
        "pipeline_version": 1,
        "schema": "legacy-manifest-v1",
        "records": assigned,
        "quality_report": report,
        "status": "ready_for_manual_review",
        "training_started": False,
    }


def prepare_example_dataset(
    records: Iterable[Mapping[str, Any]],
    *,
    ratios: Mapping[str, float] | None = None,
    dataset_origin: str = "synthetic_fixture",
) -> dict[str, Any]:
    """Assign safe splits and report quality for example-level records."""
    assigned = assign_example_splits(records, ratios=ratios)
    report = report_example_records(assigned, dataset_origin=dataset_origin)
    if report["records_invalid"]:
        raise ValueError(
            "example dataset failed post-split quality gate: "
            f"{report['records_invalid']} invalid records; "
            f"issues={report['validation_issue_counts']}"
        )
    return {
        "pipeline_version": 1,
        "schema": "axral.pitch-training-example-1.0",
        "records": assigned,
        "quality_report": report,
        "status": "ready_for_manual_review",
        "training_started": False,
    }
