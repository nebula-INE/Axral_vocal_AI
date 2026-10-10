"""Read-only adapter from VO-SE_vocal note models to Axral AI contracts.

This module creates a request snapshot only. It never mutates notes, pitch
automation, the voicebank parser, or audio/rendering state.
"""
from __future__ import annotations

from typing import Any, Callable, Optional, Sequence

from axral_vocal_ai.contracts import PitchNote, PitchRequest, VoicebankProfile

AliasResolver = Callable[[str, int], Optional[Any]]

_REST_LYRICS = {
    "", "r", "r_", "r_0", "[r]", "息", "br", "pau", "sil",
    "吸", "吸気", "息吸い", "休", "休符", "-", "ー", "~", "null",
}


def build_pitch_request(
    notes: Sequence[Any],
    *,
    alias_resolver: Optional[AliasResolver] = None,
    voicebank: Optional[VoicebankProfile] = None,
    tempo_bpm: Optional[float] = None,
    time_signature: Optional[tuple[int, int]] = None,
    request_id: Optional[str] = None,
) -> PitchRequest:
    """Convert NoteEvent-like objects without modifying them.

    Required attributes: note_number, start_time, duration, lyric.
    The resolver receives (original_lyric, midi_note) and may return an alias
    string, an OtoEntry-like object with an alias attribute, or None.
    Resolver exceptions intentionally propagate rather than hiding failures.

    PitchEvent automation is deliberately excluded. Its value domain is not
    semitones; do not convert it without an explicit calibrated policy.
    """
    converted: list[PitchNote] = []
    for note in notes:
        lyric = getattr(note, "lyric", None)
        if lyric is None:
            lyric = getattr(note, "lyrics", "")
        if not isinstance(lyric, str):
            raise TypeError("note lyric must be a string")

        midi_note = getattr(note, "note_number")
        start_sec = getattr(note, "start_time")
        duration = getattr(note, "duration")
        end_sec = start_sec + duration

        is_rest = lyric.strip().lower() in _REST_LYRICS
        resolved_alias: Optional[str] = None
        if alias_resolver is not None and not is_rest:
            resolved = alias_resolver(lyric, int(midi_note))
            if isinstance(resolved, str):
                resolved_alias = resolved
            elif resolved is not None:
                alias_value = getattr(resolved, "alias", None)
                if isinstance(alias_value, str):
                    resolved_alias = alias_value

        voiced: Optional[bool] = False if is_rest else (True if resolved_alias else None)
        converted.append(PitchNote(
            start_sec=start_sec,
            end_sec=end_sec,
            midi_note=midi_note,
            lyric=lyric,
            resolved_alias=resolved_alias,
            voiced=voiced,
        ))

    return PitchRequest(
        notes=tuple(converted),
        voicebank=voicebank,
        tempo_bpm=tempo_bpm,
        time_signature=time_signature,
        request_id=request_id,
    )



def make_oto_alias_resolver(oto_parser: Any) -> AliasResolver:
    """Adapt VO-SE_vocal's existing OtoParser without duplicating its rules.

    Uses resolve_alias(lyric, note_num=...) so VCV/CV fallback, rest handling,
    scoped multipitch aliases, and prefix.map selection remain owned by the app.
    """
    resolve = getattr(oto_parser, "resolve_alias", None)
    if not callable(resolve):
        raise TypeError("oto_parser must provide callable resolve_alias")

    def resolve_for_note(lyric: str, midi_note: int) -> Optional[Any]:
        return resolve(lyric, note_num=midi_note)

    return resolve_for_note
