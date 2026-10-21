"""Conservative metadata-only readiness gate for pitch-training candidates.

A positive result only means the metadata meets these mechanical checks. It is
not legal approval, a data-quality certification, or permission to start training.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from .pitch_training_quality import report_example_records, report_legacy_records

_SPLITS = ("train", "validation", "test")


def assess_training_candidate(
    records: Iterable[Mapping[str, Any]],
    *,
    schema: str,
    dataset_origin: str = "synthetic_fixture",
) -> dict[str, Any]:
    """Assess whether a prepared dataset can proceed to human training review.

    Supported schema values are legacy-manifest-v1 and
    axral.pitch-training-example-1.0. This function never starts training.
    """
    rows = [dict(row) if isinstance(row, Mapping) else row for row in records]
    if schema == "legacy-manifest-v1":
        report = report_legacy_records(rows, dataset_origin=dataset_origin)
        label_is_valid = lambda row: (
            isinstance(row, dict)
            and isinstance(row.get("target"), dict)
            and isinstance(row["target"].get("points"), list)
            and bool(row["target"]["points"])
        )
        consent_is_valid = lambda row: isinstance(row, dict) and row.get("permission_status") == "approved"
        review_is_valid = lambda row: (
            isinstance(row, dict)
            and isinstance(row.get("provenance"), dict)
            and row["provenance"].get("review_status") == "approved"
        )
    elif schema == "axral.pitch-training-example-1.0":
        report = report_example_records(rows, dataset_origin=dataset_origin)
        label_is_valid = lambda row: (
            isinstance(row, dict)
            and isinstance(row.get("target"), dict)
            and isinstance(row["target"].get("points"), list)
            and bool(row["target"]["points"])
        )
        consent_is_valid = lambda row: (
            isinstance(row, dict)
            and isinstance(row.get("provenance"), dict)
            and row["provenance"].get("consent_status") == "verified"
        )
        review_is_valid = lambda row: (
            isinstance(row, dict)
            and isinstance(row.get("target"), dict)
            and row["target"].get("review_status") == "approved"
        )
    else:
        raise ValueError(
            "schema must be legacy-manifest-v1 or axral.pitch-training-example-1.0"
        )

    reasons: list[str] = []
    if dataset_origin != "candidate_real_data":
        reasons.append("dataset_origin_not_candidate_real_data")
    if report["records_total"] == 0:
        reasons.append("empty_dataset")
    if report["records_invalid"]:
        reasons.append("invalid_records_or_split_leakage")
    if report["synthetic_or_fixture_records"]:
        reasons.append("synthetic_or_fixture_records_present")
    if report["origin_unclassified_records"]:
        reasons.append("source_origin_unclassified")
    if any(report["records_by_split"][split] == 0 for split in _SPLITS):
        reasons.append("required_split_empty")
    if not rows or any(not label_is_valid(row) for row in rows):
        reasons.append("missing_or_unreviewed_pitch_labels")
    if not rows or any(not consent_is_valid(row) for row in rows):
        reasons.append("consent_or_permission_not_verified")
    if not rows or any(not review_is_valid(row) for row in rows):
        reasons.append("manual_review_not_approved")

    groups_by_split: dict[str, set[str]] = {split: set() for split in _SPLITS}
    for row in rows:
        if not isinstance(row, dict) or row.get("split") not in _SPLITS:
            continue
        split = row["split"]
        if schema == "legacy-manifest-v1":
            value = row.get("voicebank_id")
        else:
            voicebank = row.get("voicebank")
            value = voicebank.get("split_group") if isinstance(voicebank, dict) else None
        if isinstance(value, str) and value.strip():
            groups_by_split[split].add(value.strip())
    if len(set().union(*groups_by_split.values())) < 3:
        reasons.append("fewer_than_three_independent_voicebank_groups")
    if any(not groups_by_split[split] for split in _SPLITS):
        reasons.append("split_missing_voicebank_group")

    reasons = list(dict.fromkeys(reasons))
    return {
        "readiness_version": 1,
        "schema": schema,
        "status": "blocked" if reasons else "candidate_for_human_training_review",
        "reasons": reasons,
        "records_total": report["records_total"],
        "records_valid": report["records_valid"],
        "records_invalid": report["records_invalid"],
        "records_by_split": report["records_by_split"],
        "voicebank_groups_by_split": {
            split: len(groups_by_split[split]) for split in _SPLITS
        },
        "dataset_origin": dataset_origin,
        "training_started": False,
        "authorization_warning": (
            "This metadata gate is not legal approval, does not verify source claims, "
            "and does not authorize training. Human review of permissions, provenance, "
            "labels, and evaluation isolation is still required."
        ),
    }
