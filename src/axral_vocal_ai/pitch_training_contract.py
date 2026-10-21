"""Strict JSONL validator for the axral.pitch-training-example v1 contract.

Metadata-only: this module never reads audio, executes dataset content, repairs
labels, or writes to the source manifest.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
import math
from typing import Any, Mapping

RECORD_SCHEMA = "axral.pitch-training-example"
SCHEMA_VERSION = "1.0"
_NO_OP_MARKERS = {
    "deterministic-no-op-stub", "deterministic_no_op_stub",
    "no-op-stub", "noop_stub", "no_op_stub",
}


@dataclass(frozen=True)
class RecordIssue:
    line_number: int
    example_id: str | None
    code: str
    message: str


@dataclass(frozen=True)
class JSONLValidationReport:
    accepted: tuple[Mapping[str, Any], ...]
    rejected: tuple[RecordIssue, ...]

    @property
    def accepted_count(self) -> int:
        return len(self.accepted)

    @property
    def rejected_count(self) -> int:
        return len(self.rejected)

    @property
    def rejection_counts(self) -> dict[str, int]:
        return dict(Counter(issue.code for issue in self.rejected))


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_finite(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        return False


def _is_no_op(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.strip().lower().replace(" ", "-")
    return normalized in _NO_OP_MARKERS


def validate_record(record: Any) -> tuple[tuple[str, str], ...]:
    """Return (code, message) issues for one record; no issues means valid."""
    issues: list[tuple[str, str]] = []

    def check(condition: bool, code: str, message: str) -> None:
        if not condition:
            issues.append((code, message))

    check(isinstance(record, dict), "record_not_object", "record must be a JSON object")
    if not isinstance(record, dict):
        return tuple(issues)

    check(record.get("record_schema") == RECORD_SCHEMA, "unsupported_schema",
          "record_schema must be axral.pitch-training-example")
    check(record.get("schema_version") == SCHEMA_VERSION, "unsupported_version",
          "schema_version must be 1.0")
    check(_is_text(record.get("example_id")), "missing_example_id",
          "example_id must be a non-empty stable identifier")

    provenance = record.get("provenance")
    check(isinstance(provenance, dict), "invalid_provenance", "provenance must be an object")
    if isinstance(provenance, dict):
        for field in ("source_kind", "source_id", "license_or_permission", "consent_status", "created_at"):
            check(_is_text(provenance.get(field)), "missing_provenance",
                  f"provenance.{field} must be a non-empty string")
        check(provenance.get("consent_status") == "verified", "permission_not_verified",
              "consent_status must be verified")
        check(not _is_no_op(provenance.get("source_kind")), "stub_is_not_label",
              "deterministic no-op stub output cannot be training ground truth")

    voicebank = record.get("voicebank")
    check(isinstance(voicebank, dict), "invalid_voicebank", "voicebank must be an object")
    if isinstance(voicebank, dict):
        for field in ("profile_id", "profile_version", "phoneme_scheme", "split_group"):
            check(_is_text(voicebank.get(field)), "missing_voicebank_field",
                  f"voicebank.{field} must be a non-empty string")

    context = record.get("context")
    check(isinstance(context, dict), "invalid_context", "context must be an object")
    duration: float | None = None
    voiced: bool | None = None
    if isinstance(context, dict):
        midi = context.get("midi_note")
        check(type(midi) is int and 0 <= midi <= 127, "invalid_midi_note",
              "context.midi_note must be an integer in 0..127")
        for field in ("start_ms", "duration_ms"):
            check(_is_finite(context.get(field)), "invalid_time",
                  f"context.{field} must be a finite number")
        if _is_finite(context.get("start_ms")):
            check(float(context["start_ms"]) >= 0, "invalid_start",
                  "context.start_ms must be non-negative")
        if _is_finite(context.get("duration_ms")):
            duration = float(context["duration_ms"])
            check(duration >= 0, "negative_duration", "context.duration_ms must be non-negative")
        check(_is_text(context.get("lyric")), "missing_lyric",
              "context.lyric must be a non-empty string")
        check(_is_text(context.get("resolved_alias")), "alias_unresolved",
              "context.resolved_alias must be a non-empty resolved alias")
        check(isinstance(context.get("voiced"), bool), "invalid_voiced_flag",
              "context.voiced must be a boolean")
        if isinstance(context.get("voiced"), bool):
            voiced = context["voiced"]

        baseline = context.get("baseline_pitch")
        check(isinstance(baseline, list), "invalid_baseline",
              "context.baseline_pitch must be a list")
        if isinstance(baseline, list):
            check(bool(baseline) or voiced is False, "empty_baseline",
                  "voiced notes require baseline pitch points")
            previous_time = -math.inf
            for index, point in enumerate(baseline):
                prefix = f"context.baseline_pitch[{index}]"
                if not isinstance(point, dict):
                    check(False, "invalid_baseline_point", f"{prefix} must be an object")
                    continue
                time_ms, hz = point.get("time_ms"), point.get("hz")
                check(_is_finite(time_ms), "invalid_baseline_time",
                      f"{prefix}.time_ms must be finite")
                check(_is_finite(hz) and float(hz) > 0, "invalid_baseline_hz",
                      f"{prefix}.hz must be finite and greater than zero")
                if _is_finite(time_ms):
                    current = float(time_ms)
                    check(current >= previous_time, "unordered_baseline",
                          "baseline pitch points must be ordered by time")
                    check(current >= 0 and (duration is None or current <= duration),
                          "baseline_out_of_range", "baseline pitch times must fall within note duration")
                    previous_time = current

    target = record.get("target")
    check(isinstance(target, dict), "invalid_target", "target must be an object")
    if isinstance(target, dict):
        check(target.get("kind") == "pitch_delta", "unsupported_target",
              "target.kind must be pitch_delta")
        check(_is_text(target.get("label_source")), "missing_label_source",
              "target.label_source must be a non-empty string")
        check(not _is_no_op(target.get("label_source")), "stub_is_not_label",
              "deterministic no-op stub output cannot be training ground truth")
        check(target.get("review_status") == "approved", "label_not_approved",
              "target.review_status must be approved")
        points = target.get("points")
        check(isinstance(points, list), "invalid_target_points", "target.points must be a list")
        if isinstance(points, list):
            if voiced is True:
                check(bool(points), "missing_target_points",
                      "voiced notes require at least one pitch-delta point")
            if voiced is False:
                check(not points, "unvoiced_target",
                      "unvoiced/rest context cannot contain pitch-delta points")
            previous_time = -math.inf
            for index, point in enumerate(points):
                prefix = f"target.points[{index}]"
                if not isinstance(point, dict):
                    check(False, "invalid_target_point", f"{prefix} must be an object")
                    continue
                time_ms, delta = point.get("time_ms"), point.get("delta_cents")
                check(_is_finite(time_ms), "invalid_target_time", f"{prefix}.time_ms must be finite")
                check(_is_finite(delta), "invalid_delta", f"{prefix}.delta_cents must be finite")
                if _is_finite(time_ms):
                    current = float(time_ms)
                    check(current >= previous_time, "unordered_target",
                          "target points must be ordered by time")
                    check(current >= 0 and (duration is None or current <= duration),
                          "target_out_of_range", "target point times must fall within note duration")
                    previous_time = current

    return tuple(issues)


def validate_jsonl_text(text: str) -> JSONLValidationReport:
    """Validate JSON Lines text and reject every occurrence of a duplicate ID."""
    parsed: list[tuple[int, Any, tuple[tuple[str, str], ...], str | None]] = []
    rejected: list[RecordIssue] = []
    ids: Counter[str] = Counter()

    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            rejected.append(RecordIssue(line_number, None, "invalid_json", "line is not valid JSON"))
            continue
        example_id = (
            record.get("example_id")
            if isinstance(record, dict) and _is_text(record.get("example_id"))
            else None
        )
        parsed.append((line_number, record, validate_record(record), example_id))
        if example_id is not None:
            ids[example_id] += 1

    accepted: list[Mapping[str, Any]] = []
    for line_number, record, issues, example_id in parsed:
        if example_id is not None and ids[example_id] > 1:
            rejected.append(RecordIssue(
                line_number, example_id, "duplicate_example_id",
                "example_id occurs more than once in this JSONL input",
            ))
            continue
        if issues:
            rejected.extend(
                RecordIssue(line_number, example_id, code, message)
                for code, message in issues
            )
            continue
        accepted.append(record)

    rejected.sort(key=lambda issue: (issue.line_number, issue.code))
    return JSONLValidationReport(tuple(accepted), tuple(rejected))
