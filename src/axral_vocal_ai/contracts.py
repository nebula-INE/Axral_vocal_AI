"""Versioned, renderer-independent contracts for Axral Vocal AI.

These data structures describe proposals only. They do not edit VO-SE_vocal
notes or pitch curves and do not perform audio synthesis.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Literal, Optional, Sequence

SCHEMA_VERSION = 1
PitchStatus = Literal["ok", "no_change", "rejected"]


def _finite(value: float, field_name: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite")


@dataclass(frozen=True)
class PitchNote:
    """Minimal note context; times are seconds and pitch is MIDI note number."""

    start_sec: float
    end_sec: float
    midi_note: float
    lyric: str
    resolved_alias: Optional[str] = None
    voiced: Optional[bool] = None

    def __post_init__(self) -> None:
        _finite(self.start_sec, "start_sec")
        _finite(self.end_sec, "end_sec")
        _finite(self.midi_note, "midi_note")
        if self.end_sec < self.start_sec:
            raise ValueError("end_sec must be greater than or equal to start_sec")
        if not 0 <= self.midi_note <= 127:
            raise ValueError("midi_note must be in the MIDI range 0..127")
        if not isinstance(self.lyric, str):
            raise TypeError("lyric must be a string")
        if self.resolved_alias is not None and not isinstance(self.resolved_alias, str):
            raise TypeError("resolved_alias must be a string or None")
        if self.voiced is not None and not isinstance(self.voiced, bool):
            raise TypeError("voiced must be a bool or None")


@dataclass(frozen=True)
class VoicebankProfile:
    """Non-sensitive summary derived from the existing voicebank parser."""

    alias_count: int = 0
    sample_count: int = 0
    phoneme_inventory: Sequence[str] = ()
    pitch_bank_boundaries: Sequence[float] = ()
    parser_version: Optional[str] = None
    format_hints: Sequence[str] = ()

    def __post_init__(self) -> None:
        if self.alias_count < 0 or self.sample_count < 0:
            raise ValueError("voicebank counts cannot be negative")
        for value in self.pitch_bank_boundaries:
            _finite(value, "pitch_bank_boundaries entry")


@dataclass(frozen=True)
class PitchRequest:
    notes: Sequence[PitchNote]
    voicebank: Optional[VoicebankProfile] = None
    tempo_bpm: Optional[float] = None
    time_signature: Optional[tuple[int, int]] = None
    request_id: Optional[str] = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"unsupported request schema_version: {self.schema_version}")
        previous_start: Optional[float] = None
        for note in self.notes:
            if previous_start is not None and note.start_sec < previous_start:
                raise ValueError("notes must be ordered by start_sec")
            previous_start = note.start_sec
        if self.tempo_bpm is not None:
            _finite(self.tempo_bpm, "tempo_bpm")
            if self.tempo_bpm <= 0:
                raise ValueError("tempo_bpm must be greater than zero")
        if self.time_signature is not None:
            numerator, denominator = self.time_signature
            if numerator <= 0 or denominator <= 0:
                raise ValueError("time signature values must be positive")


@dataclass(frozen=True)
class PitchDeltaPoint:
    """Proposed pitch offset at a time, in seconds and semitones."""

    time_sec: float
    delta_semitones: float

    def __post_init__(self) -> None:
        _finite(self.time_sec, "time_sec")
        _finite(self.delta_semitones, "delta_semitones")


@dataclass(frozen=True)
class PitchResponse:
    status: PitchStatus
    pitch_deltas: Sequence[PitchDeltaPoint] = ()
    warnings: Sequence[str] = ()
    request_id: Optional[str] = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"unsupported response schema_version: {self.schema_version}")
        if self.status not in ("ok", "no_change", "rejected"):
            raise ValueError(f"unsupported response status: {self.status}")
        previous_time: Optional[float] = None
        for point in self.pitch_deltas:
            if previous_time is not None and point.time_sec < previous_time:
                raise ValueError("pitch_deltas must be ordered by time_sec")
            previous_time = point.time_sec
        if self.status != "ok" and self.pitch_deltas:
            raise ValueError("only an 'ok' response may contain pitch_deltas")


def request_from_dict(payload: Dict[str, Any]) -> PitchRequest:
    """Parse and validate a plain dictionary at an API/file boundary."""
    if payload.get("schema_version", SCHEMA_VERSION) != SCHEMA_VERSION:
        raise ValueError("unsupported request schema_version")
    raw_notes = payload.get("notes")
    if not isinstance(raw_notes, list):
        raise ValueError("notes must be a list")
    notes = [PitchNote(**item) for item in raw_notes]
    raw_voicebank = payload.get("voicebank")
    voicebank = VoicebankProfile(**raw_voicebank) if raw_voicebank is not None else None
    signature = payload.get("time_signature")
    return PitchRequest(
        notes=notes,
        voicebank=voicebank,
        tempo_bpm=payload.get("tempo_bpm"),
        time_signature=tuple(signature) if signature is not None else None,
        request_id=payload.get("request_id"),
        schema_version=payload.get("schema_version", SCHEMA_VERSION),
    )


def response_from_dict(payload: Dict[str, Any]) -> PitchResponse:
    """Parse and validate a plain dictionary at an API/file boundary."""
    if payload.get("schema_version", SCHEMA_VERSION) != SCHEMA_VERSION:
        raise ValueError("unsupported response schema_version")
    raw_points = payload.get("pitch_deltas", [])
    if not isinstance(raw_points, list):
        raise ValueError("pitch_deltas must be a list")
    if any(not isinstance(item, dict) for item in raw_points):
        raise ValueError("pitch_deltas entries must be objects")
    points = [PitchDeltaPoint(**item) for item in raw_points]
    return PitchResponse(
        status=payload.get("status", "rejected"),
        pitch_deltas=points,
        warnings=payload.get("warnings", []),
        request_id=payload.get("request_id"),
        schema_version=payload.get("schema_version", SCHEMA_VERSION),
    )
