"""Build a conservative wire-v1 request from audited voicebank metadata.

This module only assembles JSON metadata. It does not read WAV bytes, invoke a
model, alter notes, or connect to any renderer/export/audio-processing path.
Ambiguous alias or prefix-map selection fails closed instead of guessing.
"""
from __future__ import annotations

from collections import Counter
from pathlib import PurePosixPath
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
    if not isinstance(profile_version, str) or not profile_version.strip():
        raise WireRequestBuildError("profile_version must be a non-empty string")
    if isinstance(strength, bool) or not isinstance(strength, (int, float)) or not 0 <= strength <= 1:
        raise WireRequestBuildError("strength must be a number in [0, 1]")
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
    for index, raw_note in enumerate(notes):
        if not isinstance(raw_note, Mapping):
            raise WireRequestBuildError(f"notes[{index}] must be a mapping")
        note_id = raw_note.get("note_id")
        if not isinstance(note_id, str) or not note_id.strip():
            raise WireRequestBuildError(f"notes[{index}].note_id must be a non-empty string")
        alias = raw_note.get("alias")
        midi = raw_note.get("midi_note")
        if not isinstance(alias, str) or not alias:
            raise WireRequestBuildError("alias must be a non-empty string", note_id=note_id)
        if type(midi) is not int or not 0 <= midi <= 127:
            raise WireRequestBuildError("midi_note must be an integer in 0..127", note_id=note_id)

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
        relative = PurePosixPath(entry.wav_filename)
        if relative.is_absolute() or ".." in relative.parts or not entry.wav_filename:
            raise WireRequestBuildError(
                f"note {note_id}: sample path is not a safe voicebank-relative path",
                note_id=note_id,
                status="error",
            )
        wire_note: dict[str, Any] = {
            "note_id": note_id,
            "midi_note": midi,
            "start_ms": raw_note.get("start_ms"),
            "duration_ms": raw_note.get("duration_ms"),
            "lyric": raw_note.get("lyric", alias),
            "resolved_alias": resolution.mapped_alias,
            "sample_ref": f"voicebank://{profile_id}/{relative.as_posix()}",
            "voiced": raw_note.get("voiced", True),
        }
        if "baseline_pitch" in raw_note:
            wire_note["baseline_pitch"] = raw_note["baseline_pitch"]
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
