"""Build a conservative wire-v1 request from audited voicebank metadata.

This module only assembles JSON metadata. It does not read WAV bytes, invoke a
model, alter notes, or connect to any renderer/export/audio-processing path.
Ambiguous alias or prefix-map selection fails closed instead of guessing.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Mapping, Sequence
from uuid import uuid4

from axral_vocal_ai.voicebank_analysis import VoicebankAnalysis
from axral_vocal_ai.voicebank_alias import resolve_utau_alias

REQUEST_CONTRACT = "axral.vocal-expression.request"
WIRE_VERSION = "1.0"


class WireRequestBuildError(ValueError):
    """Request metadata could not be resolved safely."""

    def __init__(self, message: str, *, note_id: str | None = None, status: str | None = None):
        super().__init__(message)
        self.note_id = note_id
        self.status = status


def _nonnegative_finite(value: Any, field: str, *, note_id: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WireRequestBuildError(f"{field} must be a finite non-negative number", note_id=note_id)
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise WireRequestBuildError(f"{field} must be a finite non-negative number", note_id=note_id)
    return result


def _validated_baseline_pitch(value: Any, duration_ms: float, *, note_id: str) -> list[dict[str, float]]:
    """Validate and copy note-relative baseline pitch points for wire v1."""
    if not isinstance(value, list):
        raise WireRequestBuildError("baseline_pitch must be a list", note_id=note_id)
    result: list[dict[str, float]] = []
    previous_ms = -math.inf
    for index, point in enumerate(value):
        if not isinstance(point, Mapping):
            raise WireRequestBuildError(
                f"baseline_pitch[{index}] must be a mapping", note_id=note_id
            )
        time_ms = point.get("time_ms")
        hz = point.get("hz")
        if (
            isinstance(time_ms, bool) or not isinstance(time_ms, (int, float))
            or not math.isfinite(float(time_ms))
        ):
            raise WireRequestBuildError(
                f"baseline_pitch[{index}].time_ms must be finite", note_id=note_id
            )
        if isinstance(hz, bool) or not isinstance(hz, (int, float)) or not math.isfinite(float(hz)):
            raise WireRequestBuildError(
                f"baseline_pitch[{index}].hz must be finite", note_id=note_id
            )
        time_value, hz_value = float(time_ms), float(hz)
        if time_value < previous_ms:
            raise WireRequestBuildError("baseline_pitch must be time-ordered", note_id=note_id)
        if time_value < 0 or time_value > duration_ms:
            raise WireRequestBuildError(
                "baseline_pitch time_ms must fall within note duration", note_id=note_id
            )
        if hz_value <= 0:
            raise WireRequestBuildError("baseline_pitch hz must be greater than zero", note_id=note_id)
        result.append({"time_ms": time_value, "hz": hz_value})
        previous_ms = time_value
    return result


def build_wire_request(
    analysis: VoicebankAnalysis,
    notes: Sequence[Mapping[str, Any]],
    *,
    profile_id: str,
    profile_version: str,
    request_id: str | None = None,
    strength: float = 1.0,
) -> dict[str, Any]:
    """Resolve note aliases against an analysis report and emit wire request v1.

    Each input note must provide note_id, midi_note, start_ms, duration_ms and
    alias. Optional lyric, voiced, and baseline_pitch are copied as metadata.
    sample_ref is a voicebank-scoped URI, never an absolute local filesystem path.
    """
    if not isinstance(profile_id, str) or not profile_id.strip():
        raise WireRequestBuildError("profile_id must be a non-empty string")
    # profile_id is interpolated into the URI authority component. Keep it to
    # one conservative identifier segment so callers cannot inject URI syntax.
    if (
        profile_id in {".", ".."}
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", profile_id)
    ):
        raise WireRequestBuildError(
            "profile_id must be a 1-128 character URI-safe identifier"
        )
    if not isinstance(profile_version, str) or not profile_version.strip():
        raise WireRequestBuildError("profile_version must be a non-empty string")
    if request_id is not None and (not isinstance(request_id, str) or not request_id.strip()):
        raise WireRequestBuildError("request_id must be a non-empty string when supplied")
    if isinstance(strength, bool) or not isinstance(strength, (int, float)) or not math.isfinite(float(strength)) or not 0 <= strength <= 1:
        raise WireRequestBuildError("strength must be a finite number in [0, 1]")
    if not isinstance(notes, Sequence) or isinstance(notes, (str, bytes)):
        raise WireRequestBuildError("notes must be a sequence")

    boundaries = Counter(entry.boundary for entry in analysis.prefix_entries)
    duplicated = sorted(boundary for boundary, count in boundaries.items() if count > 1)
    if duplicated:
        raise WireRequestBuildError(
            "prefix.map contains duplicate MIDI boundaries; selection is ambiguous: "
            + ", ".join(map(str, duplicated)),
            status="needs_review",
        )
    if any(issue.code in {"prefix_map_boundary_conflict", "nested_prefix_map"} for issue in analysis.issues):
        raise WireRequestBuildError(
            "multiple/nested prefix.map files require renderer-specific selection review",
            status="needs_review",
        )

    wire_notes: list[dict[str, Any]] = []
    seen_note_ids: set[str] = set()
    for index, raw_note in enumerate(notes):
        if not isinstance(raw_note, Mapping):
            raise WireRequestBuildError(f"notes[{index}] must be a mapping")
        note_id = raw_note.get("note_id")
        if not isinstance(note_id, str) or not note_id.strip():
            raise WireRequestBuildError(f"notes[{index}].note_id must be a non-empty string")
        if note_id in seen_note_ids:
            raise WireRequestBuildError(f"duplicate note_id in request: {note_id}", note_id=note_id)
        seen_note_ids.add(note_id)
        alias = raw_note.get("alias")
        midi = raw_note.get("midi_note")
        if not isinstance(alias, str) or not alias:
            raise WireRequestBuildError("alias must be a non-empty string", note_id=note_id)
        if type(midi) is not int or not 0 <= midi <= 127:
            raise WireRequestBuildError("midi_note must be an integer in 0..127", note_id=note_id)
        start_ms = _nonnegative_finite(raw_note.get("start_ms"), "start_ms", note_id=note_id)
        duration_ms = _nonnegative_finite(raw_note.get("duration_ms"), "duration_ms", note_id=note_id)
        voiced = raw_note.get("voiced", True)
        if not isinstance(voiced, bool):
            raise WireRequestBuildError("voiced must be a boolean", note_id=note_id)
        lyric = raw_note.get("lyric", alias)
        if not isinstance(lyric, str):
            raise WireRequestBuildError("lyric must be a string", note_id=note_id)

        resolution = resolve_utau_alias(
            alias, midi, analysis.entries, analysis.prefix_entries, analysis.root
        )
        if resolution.status != "resolved" or len(resolution.candidates) != 1:
            raise WireRequestBuildError(
                f"note {note_id}: alias resolution is {resolution.status}; no sample was selected",
                note_id=note_id,
                status="needs_review" if resolution.status == "ambiguous" else "error",
            )
        candidate = resolution.candidates[0]
        entry = candidate.entry
        filename = entry.wav_filename
        relative = PurePosixPath(filename) if isinstance(filename, str) else PurePosixPath(".")
        windows_path = PureWindowsPath(filename) if isinstance(filename, str) else PureWindowsPath(".")
        if (
            not isinstance(filename, str) or not filename.strip()
            or relative.is_absolute() or windows_path.is_absolute() or windows_path.drive
            or "\\" in filename or ".." in relative.parts or relative.as_posix() in {"", "."}
        ):
            raise WireRequestBuildError(
                f"note {note_id}: sample path is not a safe voicebank-relative path",
                note_id=note_id,
                status="error",
            )
        wire_note: dict[str, Any] = {
            "note_id": note_id,
            "midi_note": midi,
            "start_ms": start_ms,
            "duration_ms": duration_ms,
            "lyric": lyric,
            "resolved_alias": resolution.mapped_alias,
            "sample_ref": f"voicebank://{profile_id}/{relative.as_posix()}",
            "voiced": voiced,
        }
        if "baseline_pitch" in raw_note:
            wire_note["baseline_pitch"] = _validated_baseline_pitch(
                raw_note["baseline_pitch"], duration_ms, note_id=note_id
            )
        wire_notes.append(wire_note)

    return {
        "contract": REQUEST_CONTRACT,
        "schema_version": WIRE_VERSION,
        "request_id": request_id or f"wire-{uuid4().hex}",
        "voicebank": {
            "profile_id": profile_id,
            "profile_version": profile_version,
            "alias_resolution_status": "resolved",
        },
        "notes": wire_notes,
        "controls": {"enabled_features": ["pitch_delta"], "strength": float(strength)},
    }
