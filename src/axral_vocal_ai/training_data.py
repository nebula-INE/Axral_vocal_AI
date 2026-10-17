"""Strict metadata-only validation for Axral Vocal AI training manifests.

This module never loads audio, opens source paths, or starts model training.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable

PERMISSION_STATES = {"approved", "review_required", "prohibited"}
SPLITS = {"train", "validation", "test"}
TARGET_KIND = "pitch_delta_semitones"
MAX_TRAINING_DELTA_SEMITONES = 2.0
FORBIDDEN_KEYS = {"audio", "audio_bytes", "audio_file", "audio_path", "waveform", "wav_path", "file_path", "source_path", "relative_path", "absolute_path", "local_path", "checkpoint", "credentials", "token", "secret"}


class DatasetValidationError(ValueError):
    """Raised when a dataset manifest violates the training gate."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DatasetValidationError(message)


def _finite_number(value: Any, label: str) -> float:
    _require(isinstance(value, (int, float)) and not isinstance(value, bool), f"{label} must be numeric")
    try:
        number = float(value)
    except (OverflowError, ValueError):
        raise DatasetValidationError(f"{label} must be finite") from None
    _require(math.isfinite(number), f"{label} must be finite")
    return number


def _check_no_private_payload(value: Any, location: str = "record") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            _require(normalized not in FORBIDDEN_KEYS, f"{location}.{key} is not allowed in a metadata manifest")
            _check_no_private_payload(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _check_no_private_payload(child, f"{location}[{index}]")
    elif isinstance(value, str):
        # Catch common local filesystem paths without rejecting ordinary URLs or opaque IDs.
        _require(not value.startswith(("/", "~/", "./", "../")), f"{location} must not contain a local filesystem path")
        _require(not (value.startswith("\\\\") or (len(value) > 2 and value[1] == ":" and value[2] in "\\\\/")), f"{location} must not contain a Windows filesystem path")


def validate_record(record: Any, line_number: int, require_labeled: bool = False) -> dict[str, Any]:
    prefix = f"line {line_number}"
    _require(isinstance(record, dict), f"{prefix}: each JSONL row must be an object")
    _check_no_private_payload(record, prefix)

    required = {
        "schema_version", "record_id", "source_id", "permission_status",
        "license_id", "voicebank_id", "split", "input", "target",
        "provenance", "preprocessing",
    }
    missing = sorted(required - record.keys())
    _require(not missing, f"{prefix}: missing required fields: {', '.join(missing)}")
    _require(type(record["schema_version"]) is int and record["schema_version"] == 1, f"{prefix}: schema_version must be 1")

    for field in ("record_id", "source_id", "voicebank_id"):
        _require(isinstance(record[field], str) and bool(record[field].strip()), f"{prefix}: {field} must be a non-empty string")

    permission = record["permission_status"]
    _require(isinstance(permission, str) and permission in PERMISSION_STATES, f"{prefix}: invalid permission_status")
    _require(permission == "approved", f"{prefix}: source is not approved for ML use (status={permission})")
    license_id = record["license_id"]
    _require(isinstance(license_id, str) and bool(license_id.strip()), f"{prefix}: approved records require a non-empty license_id")

    _require(isinstance(record["split"], str) and record["split"] in SPLITS, f"{prefix}: split must be train, validation, or test")
    input_data = record["input"]
    _require(isinstance(input_data, dict), f"{prefix}: input must be an object")
    notes = input_data.get("notes")
    _require(isinstance(notes, list) and bool(notes), f"{prefix}: input.notes must be a non-empty list")
    previous_start = -math.inf
    note_starts: list[float] = []
    note_ends: list[float] = []
    for index, note in enumerate(notes):
        where = f"{prefix}: input.notes[{index}]"
        _require(isinstance(note, dict), f"{where} must be an object")
        for field in ("start_sec", "end_sec", "midi_note", "lyric"):
            _require(field in note, f"{where} missing {field}")
        start = _finite_number(note["start_sec"], f"{where}.start_sec")
        end = _finite_number(note["end_sec"], f"{where}.end_sec")
        midi = _finite_number(note["midi_note"], f"{where}.midi_note")
        _require(start >= 0 and end > start, f"{where} must have non-negative start and positive duration")
        _require(start >= previous_start, f"{prefix}: notes must be ordered by start_sec")
        _require(0 <= midi <= 127, f"{where}.midi_note must be in range 0..127")
        _require(isinstance(note["lyric"], str), f"{where}.lyric must be a string")
        if "voiced" in note:
            _require(note["voiced"] is None or isinstance(note["voiced"], bool), f"{where}.voiced must be bool or null")
        previous_start = start
        note_starts.append(start)
        note_ends.append(end)

    # Use the already validated finite numbers; converting raw values again
    # could leak OverflowError for extremely large JSON integers.
    # Labels may occur at the first/final note endpoints (some editors emit
    # endpoint samples), but must stay within the note timeline. Internal gaps
    # are allowed here and handled conservatively by feature mapping.
    note_timeline_start = min(note_starts)
    note_timeline_end = max(note_ends)

    target = record["target"]
    if require_labeled:
        _require(isinstance(target, dict), f"{prefix}: target labels are required for training")
    if target is not None:
        _require(isinstance(target, dict), f"{prefix}: target must be an object or null")
        _require(target.get("kind") == TARGET_KIND, f"{prefix}: target.kind must be {TARGET_KIND}")
        points = target.get("points")
        _require(isinstance(points, list) and bool(points), f"{prefix}: target.points must be a non-empty list")
        previous_time = -math.inf
        for index, point in enumerate(points):
            where = f"{prefix}: target.points[{index}]"
            _require(isinstance(point, dict), f"{where} must be an object")
            _require("time_sec" in point and "delta_semitones" in point, f"{where} requires time_sec and delta_semitones")
            time_sec = _finite_number(point["time_sec"], f"{where}.time_sec")
            delta = _finite_number(point["delta_semitones"], f"{where}.delta_semitones")
            _require(-MAX_TRAINING_DELTA_SEMITONES <= delta <= MAX_TRAINING_DELTA_SEMITONES,
                     f"{where}.delta_semitones must be within +/-{MAX_TRAINING_DELTA_SEMITONES} semitones")
            _require(time_sec >= 0 and time_sec > previous_time, f"{where} timestamps must be non-negative and strictly increasing")
            _require(time_sec >= note_timeline_start,
                     f"{where}.time_sec must not precede the note timeline start ({note_timeline_start})")
            _require(time_sec <= note_timeline_end,
                     f"{where}.time_sec must not exceed the note timeline end ({note_timeline_end})")
            previous_time = time_sec
        _require(isinstance(target.get("label_source"), str) and bool(target["label_source"].strip()), f"{prefix}: target.label_source is required")
        if "confidence" in target and target["confidence"] is not None:
            confidence = _finite_number(target["confidence"], f"{prefix}: target.confidence")
            _require(0 <= confidence <= 1, f"{prefix}: target.confidence must be in [0, 1]")

    provenance = record["provenance"]
    _require(isinstance(provenance, dict), f"{prefix}: provenance must be an object")
    for field in ("acquisition_method", "source_reference", "review_date", "review_status"):
        _require(field in provenance, f"{prefix}: provenance missing {field}")
    _require(provenance["review_status"] == "approved", f"{prefix}: provenance review_status must be approved")
    preprocessing = record["preprocessing"]
    _require(isinstance(preprocessing, dict), f"{prefix}: preprocessing must be an object")
    _require(isinstance(preprocessing.get("tool_version"), str) and bool(preprocessing["tool_version"].strip()), f"{prefix}: preprocessing.tool_version is required")
    _require(isinstance(preprocessing.get("transformations"), list), f"{prefix}: preprocessing.transformations must be a list")
    return record


def validate_records(records: Iterable[Any], require_labeled: bool = False) -> dict[str, Any]:
    seen_ids: set[str] = set()
    bank_splits: dict[str, str] = {}
    source_splits: dict[str, str] = {}
    counts = {split: 0 for split in sorted(SPLITS)}
    total = 0
    labeled_records = 0
    for line_number, record in enumerate(records, start=1):
        validated = validate_record(record, line_number, require_labeled=require_labeled)
        record_id = validated["record_id"]
        _require(record_id not in seen_ids, f"line {line_number}: duplicate record_id {record_id!r}")
        seen_ids.add(record_id)
        bank = validated["voicebank_id"]
        source = validated["source_id"]
        split = validated["split"]
        _require(bank not in bank_splits or bank_splits[bank] == split,
                 f"line {line_number}: voicebank {bank!r} appears in multiple splits")
        _require(source not in source_splits or source_splits[source] == split,
                 f"line {line_number}: source {source!r} appears in multiple splits")
        bank_splits[bank] = split
        source_splits[source] = split
        counts[split] += 1
        total += 1
        target = validated.get("target")
        if isinstance(target, dict) and isinstance(target.get("points"), list) and target["points"]:
            labeled_records += 1
    _require(total > 0, "dataset manifest contains no records")
    _require(any(counts[split] for split in ("train", "validation", "test")), "no split records found")
    if require_labeled:
        missing_splits = [split for split in ("train", "validation", "test") if counts[split] == 0]
        _require(not missing_splits,
                 "training readiness requires non-empty train, validation, and test splits; missing: "
                 + ", ".join(missing_splits))
        _require(len(bank_splits) >= 3,
                 "training readiness requires at least three distinct voicebanks for isolated splits")
    return {
        "status": "valid",
        "records": total,
        "labeled_records": labeled_records,
        "records_by_split": counts,
        "voicebanks_by_split": {
            split: sorted(bank for bank, bank_split in bank_splits.items() if bank_split == split)
            for split in sorted(SPLITS)
        },
        "require_labeled": require_labeled,
    }


def validate_jsonl(path: str | Path, require_labeled: bool = False) -> dict[str, Any]:
    """Validate a JSON Lines manifest; the file is metadata only, never audio."""
    manifest_path = Path(path)
    records: list[Any] = []
    try:
        with manifest_path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise DatasetValidationError(f"line {line_number}: invalid JSON: {exc.msg}") from exc
    except OSError as exc:
        raise DatasetValidationError(f"cannot read manifest: {exc}") from exc
    return validate_records(records, require_labeled=require_labeled)
