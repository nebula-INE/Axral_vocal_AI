"""Explicit adapter between wire contract v1 and the internal pitch contract.

This module only converts validated metadata proposals. It does not call a model,
edit source notes, or invoke any renderer/audio/export code.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Mapping

from .contracts import PitchDeltaPoint, PitchRequest, PitchResponse, SCHEMA_VERSION
from .response_validation import validate_pitch_response

WIRE_VERSION = "1.0"
REQUEST_CONTRACT = "axral.vocal-expression.request"
RESPONSE_CONTRACT = "axral.vocal-expression.response"
_WIRE_STATUSES = {"ok", "partial", "needs_review", "error"}
_NOTE_STATUSES = {"ok", "no_change", "needs_review", "rejected", "error"}


def _object(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def _wire_notes(request: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    raw_notes = request.get("notes")
    if not isinstance(raw_notes, list):
        raise ValueError("request notes must be a list")
    indexed: dict[str, Mapping[str, Any]] = {}
    previous_start = -math.inf
    for index, raw in enumerate(raw_notes):
        note = _object(raw, f"request notes[{index}]")
        note_id = note.get("note_id")
        if not isinstance(note_id, str) or not note_id:
            raise ValueError(f"request notes[{index}].note_id must be a non-empty string")
        if note_id in indexed:
            raise ValueError(f"duplicate note_id in request: {note_id}")
        start = _finite_number(note.get("start_ms"), f"request notes[{index}].start_ms")
        duration = _finite_number(note.get("duration_ms"), f"request notes[{index}].duration_ms")
        if start < 0 or duration < 0:
            raise ValueError("note start_ms and duration_ms must be non-negative")
        if start < previous_start:
            raise ValueError("request notes must be ordered by start_ms")
        previous_start = start
        midi = note.get("midi_note")
        if type(midi) is not int or not 0 <= midi <= 127:
            raise ValueError(f"request notes[{index}].midi_note must be an integer in 0..127")
        if "voiced" in note and not isinstance(note["voiced"], bool):
            raise ValueError(f"request notes[{index}].voiced must be a boolean")
        indexed[note_id] = note
    return indexed


def adapt_wire_response(
    wire_request: Dict[str, Any],
    wire_response: Dict[str, Any],
    *,
    max_abs_delta_semitones: float = 2.0,
) -> PitchResponse:
    """Validate wire v1 and convert it to the internal seconds/semitones contract.

    Partial/uncertain/error results are rejected as a whole because the internal
    flat pitch-delta contract cannot safely represent per-note partial status.
    """
    request = _object(wire_request, "wire request")
    response = _object(wire_response, "wire response")
    if request.get("contract") != REQUEST_CONTRACT:
        raise ValueError("unsupported request contract")
    if request.get("schema_version") != WIRE_VERSION:
        raise ValueError("unsupported wire request schema_version")
    if response.get("contract") != RESPONSE_CONTRACT:
        raise ValueError("unsupported response contract")
    if response.get("schema_version") != WIRE_VERSION:
        raise ValueError("unsupported wire response schema_version")

    request_id = request.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        raise ValueError("request_id must be a non-empty string")
    if response.get("request_id") != request_id:
        raise ValueError("response request_id is missing or does not match request")

    notes_by_id = _wire_notes(request)
    status = response.get("status")
    if status not in _WIRE_STATUSES:
        raise ValueError("unsupported wire response status")
    if status != "ok":
        raise ValueError(f"wire response status '{status}' requires review; no changes accepted")

    raw_results = response.get("note_results")
    if not isinstance(raw_results, list):
        raise ValueError("note_results must be a list")
    seen: set[str] = set()
    points: list[PitchDeltaPoint] = []
    warnings = response.get("warnings", [])
    if not isinstance(warnings, list) or any(not isinstance(item, str) for item in warnings):
        raise ValueError("response warnings must be a list of strings")
    if warnings:
        raise ValueError("wire response contains warnings and requires review")

    for index, raw in enumerate(raw_results):
        result = _object(raw, f"note_results[{index}]")
        note_id = result.get("note_id")
        if not isinstance(note_id, str) or note_id not in notes_by_id:
            raise ValueError(f"note_results[{index}] contains an unknown note_id")
        if note_id in seen:
            raise ValueError(f"duplicate note result for note_id: {note_id}")
        seen.add(note_id)
        note = notes_by_id[note_id]
        note_status = result.get("status")
        if note_status not in _NOTE_STATUSES:
            raise ValueError(f"note_results[{index}] has unsupported status")
        if note_status != "ok":
            raise ValueError(f"note {note_id} status '{note_status}' requires review")
        confidence = _finite_number(result.get("confidence"), f"note_results[{index}].confidence")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"note_results[{index}].confidence must be in [0, 1]")
        note_warnings = result.get("warnings", [])
        if not isinstance(note_warnings, list) or any(not isinstance(item, str) for item in note_warnings):
            raise ValueError(f"note_results[{index}].warnings must be a list of strings")
        if note_warnings:
            raise ValueError(f"note {note_id} has warnings and requires review")

        raw_curve = result.get("pitch_delta")
        if not isinstance(raw_curve, list):
            raise ValueError(f"note_results[{index}].pitch_delta must be a list")
        start_sec = _finite_number(note["start_ms"], f"note {note_id} start_ms") / 1000.0
        duration_sec = _finite_number(note["duration_ms"], f"note {note_id} duration_ms") / 1000.0
        previous_relative_ms = -math.inf
        for point_index, raw_point in enumerate(raw_curve):
            point = _object(raw_point, f"note_results[{index}].pitch_delta[{point_index}]")
            relative_ms = _finite_number(point.get("time_ms"), "pitch delta time_ms")
            delta_cents = _finite_number(point.get("delta_cents"), "pitch delta delta_cents")
            if relative_ms < previous_relative_ms:
                raise ValueError(f"pitch_delta for note {note_id} must be time-ordered")
            if relative_ms < 0 or relative_ms / 1000.0 > duration_sec:
                raise ValueError(f"pitch_delta for note {note_id} falls outside note duration")
            previous_relative_ms = relative_ms
            # Explicit conversion: wire times are note-relative ms, internal
            # times are absolute seconds; cents become semitones.
            points.append(PitchDeltaPoint(
                time_sec=start_sec + relative_ms / 1000.0,
                delta_semitones=delta_cents / 100.0,
            ))

    if seen != set(notes_by_id):
        missing = sorted(set(notes_by_id) - seen)
        raise ValueError(f"missing note results: {', '.join(missing)}")

    internal_notes = []
    for note_id, note in notes_by_id.items():
        start_sec = float(note["start_ms"]) / 1000.0
        duration_sec = float(note["duration_ms"]) / 1000.0
        internal_notes.append({
            "note_id": note_id,
            "start_sec": start_sec,
            "end_sec": start_sec + duration_sec,
            "midi_note": note["midi_note"],
            "lyric": note.get("lyric", ""),
            "resolved_alias": note.get("resolved_alias"),
            "voiced": note.get("voiced"),
        })
    # Internal contract does not retain note IDs, so construct it in wire order.
    internal_request = PitchRequest(
        notes=tuple(
            __import__("axral_vocal_ai.contracts", fromlist=["PitchNote"]).PitchNote(
                item["start_sec"], item["end_sec"], item["midi_note"],
                item["lyric"], item["resolved_alias"], item["voiced"]
            )
            for item in internal_notes
        ),
        request_id=request_id,
        schema_version=SCHEMA_VERSION,
    )
    internal_status = "ok" if points else "no_change"
    internal_response = PitchResponse(
        status=internal_status,
        pitch_deltas=tuple(points) if points else (),
        warnings=(),
        request_id=request_id,
        schema_version=SCHEMA_VERSION,
    )
    if points:
        validate_pitch_response(
            internal_request,
            internal_response,
            max_abs_delta_semitones=max_abs_delta_semitones,
        )
    return internal_response


def deterministic_wire_stub(wire_request: Dict[str, Any]) -> Dict[str, Any]:
    """Return a no-op-shaped v1 response for contract plumbing tests only."""
    request = _object(wire_request, "wire request")
    if request.get("contract") != REQUEST_CONTRACT or request.get("schema_version") != WIRE_VERSION:
        raise ValueError("unsupported wire request contract or schema_version")
    request_id = request.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        raise ValueError("request_id must be a non-empty string")
    notes = _wire_notes(request)
    return {
        "contract": RESPONSE_CONTRACT,
        "schema_version": WIRE_VERSION,
        "request_id": request_id,
        "status": "ok",
        "model": {"model_id": "deterministic-no-op-stub", "model_version": "1"},
        "note_results": [
            {
                "note_id": note_id,
                "status": "ok",
                "pitch_delta": [],
                "confidence": 1.0,
                "warnings": [],
            }
            for note_id in notes
        ],
        "warnings": [],
    }
