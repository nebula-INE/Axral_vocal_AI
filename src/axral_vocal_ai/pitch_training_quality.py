"""Aggregate metadata-only quality reports for the two pitch dataset schemas.

The report never loads audio or emits record IDs, lyrics, aliases, or source references.
The legacy manifest and example-level contract remain deliberately separate.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping

from .training_data import DatasetValidationError, validate_record as validate_legacy_record
from .pitch_training_contract import validate_record as validate_example_record

_SPLITS = ("train", "validation", "test")
_ORIGINS = {"synthetic_fixture", "candidate_real_data"}


def _bucket(counter: Counter[str], value: Any, fallback: str = "unknown") -> None:
    """Count a bounded category without including opaque identifiers."""
    if isinstance(value, str) and value.strip():
        counter[value.strip()[:80]] += 1
    else:
        counter[fallback] += 1


def _origin(value: str) -> str:
    if value not in _ORIGINS:
        raise ValueError("dataset_origin must be 'synthetic_fixture' or 'candidate_real_data'")
    return value


def _base_report(schema: str, records: list[Any], dataset_origin: str) -> dict[str, Any]:
    origin = _origin(dataset_origin)
    return {
        "report_version": 1,
        "schema": schema,
        "dataset_origin": origin,
        "origin_warning": (
            "Synthetic/test fixture report; not evidence of real-data quality or permission."
            if origin == "synthetic_fixture"
            else "Candidate real-data report; counts do not independently verify rights, consent, or label quality."
        ),
        "records_total": len(records),
        "records_valid": 0,
        "records_invalid": 0,
        "validation_issue_counts": {},
        "records_by_split": {split: 0 for split in _SPLITS},
        "source_kind_counts": {},
        "consent_status_counts": {},
        "review_status_counts": {},
        "label_status_counts": {},
        "voicebank_group_count": 0,
        "synthetic_or_fixture_records": 0,
        "non_synthetic_declared_records": 0,
        "origin_unclassified_records": 0,
    }


def _classify_source(record: Any, example_schema: bool) -> str:
    if not isinstance(record, dict):
        return "unknown"
    if example_schema:
        provenance = record.get("provenance")
        source_kind = provenance.get("source_kind") if isinstance(provenance, dict) else None
        candidates = [source_kind]
    else:
        provenance = record.get("provenance")
        candidates = [
            provenance.get("acquisition_method") if isinstance(provenance, dict) else None,
            provenance.get("source_reference") if isinstance(provenance, dict) else None,
        ]
    normalized = " ".join(value.lower() for value in candidates if isinstance(value, str))
    if any(token in normalized for token in ("synthetic", "fixture", "mock", "generated-test", "test-fixture")):
        return "synthetic"
    if normalized.strip():
        return "declared_non_synthetic"
    return "unknown"


def _finish_report(report: dict[str, Any], counters: dict[str, Counter[str]],
                   group_values: set[str], records: list[Any], example_schema: bool) -> dict[str, Any]:
    for name, counter in counters.items():
        report[name] = dict(sorted(counter.items()))
    report["voicebank_group_count"] = len(group_values)
    for record in records:
        category = _classify_source(record, example_schema)
        key = {
            "synthetic": "synthetic_or_fixture_records",
            "declared_non_synthetic": "non_synthetic_declared_records",
            "unknown": "origin_unclassified_records",
        }[category]
        report[key] += 1
    return report


def report_legacy_records(
    records: Iterable[Any], *, dataset_origin: str = "synthetic_fixture"
) -> dict[str, Any]:
    """Report quality indicators for legacy schema_version=1 manifest records."""
    rows = list(records)
    report = _base_report("legacy-manifest-v1", rows, dataset_origin)
    issues: Counter[str] = Counter()
    splits: Counter[str] = Counter()
    sources: Counter[str] = Counter()
    consents: Counter[str] = Counter()
    reviews: Counter[str] = Counter()
    labels: Counter[str] = Counter()
    groups: set[str] = set()
    seen_ids: Counter[str] = Counter()
    id_indices: dict[str, list[int]] = {}
    bank_split: dict[str, str] = {}
    bank_index: dict[str, int] = {}
    source_split: dict[str, str] = {}
    source_index: dict[str, int] = {}
    invalid_indices: set[int] = set()
    valid_flags: list[bool] = []

    for index, row in enumerate(rows, 1):
        error_code = None
        try:
            validate_legacy_record(row, index)
        except DatasetValidationError as exc:
            # Use the stable first clause only; never include record IDs or field values.
            message = str(exc).split(":", 1)[-1].strip().lower()
            error_code = (
                "permission_or_review" if any(t in message for t in ("approved", "permission", "review"))
                else "schema_or_field_validation"
            )
            issues[error_code] += 1
        valid_flags.append(error_code is None)
        if not isinstance(row, dict):
            _bucket(splits, None)
            _bucket(sources, None)
            _bucket(consents, None)
            _bucket(reviews, None)
            _bucket(labels, None)
            continue
        _bucket(splits, row.get("split"))
        provenance = row.get("provenance")
        _bucket(sources, provenance.get("acquisition_method") if isinstance(provenance, dict) else None)
        _bucket(consents, row.get("permission_status"))
        _bucket(reviews, provenance.get("review_status") if isinstance(provenance, dict) else None)
        target = row.get("target")
        labels["labeled" if isinstance(target, dict) and bool(target.get("points")) else "unlabeled"] += 1
        bank = row.get("voicebank_id")
        source = row.get("source_id")
        split = row.get("split")
        if isinstance(bank, str) and bank:
            groups.add(bank)
            if split in _SPLITS and bank in bank_split and bank_split[bank] != split:
                issues["voicebank_split_leakage"] += 1
                invalid_indices.update((index - 1, bank_index[bank]))
            elif split in _SPLITS:
                bank_split[bank] = split
                bank_index[bank] = index - 1
        if isinstance(source, str) and source and split in _SPLITS:
            if source in source_split and source_split[source] != split:
                issues["source_split_leakage"] += 1
                invalid_indices.update((index - 1, source_index[source]))
            else:
                source_split[source] = split
                source_index[source] = index - 1
        record_id = row.get("record_id")
        if isinstance(record_id, str) and record_id:
            seen_ids[record_id] += 1
            id_indices.setdefault(record_id, []).append(index - 1)

    for record_id, count in seen_ids.items():
        if count > 1:
            issues["duplicate_record_id"] += count
            invalid_indices.update(id_indices[record_id])
    for index in invalid_indices:
        valid_flags[index] = False
    for row, valid in zip(rows, valid_flags):
        if not valid:
            continue
        split = row.get("split") if isinstance(row, dict) else None
        if split in _SPLITS:
            report["records_by_split"][split] += 1
    report["records_valid"] = sum(valid_flags)
    report["records_invalid"] = len(rows) - report["records_valid"]
    report["validation_issue_counts"] = dict(sorted(issues.items()))
    return _finish_report(report, {
        "source_kind_counts": sources,
        "consent_status_counts": consents,
        "review_status_counts": reviews,
        "label_status_counts": labels,
    }, groups, rows, False)


def report_example_records(
    records: Iterable[Any], *, dataset_origin: str = "synthetic_fixture"
) -> dict[str, Any]:
    """Report quality indicators for axral.pitch-training-example v1 records."""
    rows = list(records)
    report = _base_report("axral.pitch-training-example-1.0", rows, dataset_origin)
    issues: Counter[str] = Counter()
    splits: Counter[str] = Counter()
    sources: Counter[str] = Counter()
    consents: Counter[str] = Counter()
    reviews: Counter[str] = Counter()
    labels: Counter[str] = Counter()
    groups: set[str] = set()
    ids: Counter[str] = Counter()
    id_indices: dict[str, list[int]] = {}
    valid_flags: list[bool] = []

    for row_index, row in enumerate(rows):
        row_issues = validate_example_record(row)
        valid_flags.append(not row_issues)
        issues.update(code for code, _message in row_issues)
        if not isinstance(row, dict):
            for counter in (splits, sources, consents, reviews, labels):
                _bucket(counter, None)
            continue
        provenance = row.get("provenance")
        voicebank = row.get("voicebank")
        target = row.get("target")
        _bucket(sources, provenance.get("source_kind") if isinstance(provenance, dict) else None)
        _bucket(consents, provenance.get("consent_status") if isinstance(provenance, dict) else None)
        _bucket(reviews, target.get("review_status") if isinstance(target, dict) else None)
        labels["labeled" if isinstance(target, dict) and bool(target.get("points")) else "unlabeled"] += 1
        if isinstance(voicebank, dict):
            group = voicebank.get("split_group")
            if isinstance(group, str) and group:
                groups.add(group)
        # This schema's split is assigned as a top-level field by the split generator.
        _bucket(splits, row.get("split"))
        example_id = row.get("example_id")
        if isinstance(example_id, str) and example_id:
            ids[example_id] += 1
            id_indices.setdefault(example_id, []).append(row_index)

    for example_id, count in ids.items():
        if count > 1:
            issues["duplicate_example_id"] += count
            for row_index in id_indices[example_id]:
                valid_flags[row_index] = False
    for row, valid in zip(rows, valid_flags):
        if not valid or not isinstance(row, dict):
            continue
        split = row.get("split")
        if split in _SPLITS:
            report["records_by_split"][split] += 1
    report["records_valid"] = sum(valid_flags)
    report["records_invalid"] = len(rows) - report["records_valid"]
    report["validation_issue_counts"] = dict(sorted(issues.items()))
    return _finish_report(report, {
        "source_kind_counts": sources,
        "consent_status_counts": consents,
        "review_status_counts": reviews,
        "label_status_counts": labels,
    }, groups, rows, True)
