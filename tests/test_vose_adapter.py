from dataclasses import dataclass

import pytest

from axral_vocal_ai.adapters.vose import build_pitch_request


@dataclass
class Note:
    note_number: int
    start_time: float
    duration: float
    lyric: str


@dataclass
class OtoEntry:
    alias: str


def test_build_request_preserves_context_and_resolved_alias():
    source = [Note(60, 0.0, 0.5, "あ"), Note(62, 0.5, 0.25, "a い")]
    before = [vars(note).copy() for note in source]
    request = build_pitch_request(
        source,
        alias_resolver=lambda lyric, midi: OtoEntry("resolved-" + lyric),
        tempo_bpm=120,
        request_id="test-1",
    )
    assert [(n.start_sec, n.end_sec, n.midi_note) for n in request.notes] == [
        (0.0, 0.5, 60), (0.5, 0.75, 62)
    ]
    assert [n.lyric for n in request.notes] == ["あ", "a い"]
    assert [n.resolved_alias for n in request.notes] == ["resolved-あ", "resolved-a い"]
    assert all(n.voiced is True for n in request.notes)
    assert [vars(note) for note in source] == before
    assert request.request_id == "test-1"


def test_unresolved_alias_stays_explicitly_unresolved():
    request = build_pitch_request(
        [Note(60, 0.0, 0.4, "missing")],
        alias_resolver=lambda _lyric, _midi: None,
    )
    assert request.notes[0].resolved_alias is None
    assert request.notes[0].voiced is None


def test_rest_is_unvoiced_and_does_not_call_resolver():
    calls = []
    request = build_pitch_request(
        [Note(60, 0.0, 0.2, "R")],
        alias_resolver=lambda lyric, midi: calls.append((lyric, midi)),
    )
    assert request.notes[0].voiced is False
    assert request.notes[0].resolved_alias is None
    assert calls == []


def test_does_not_silently_reorder_notes():
    with pytest.raises(ValueError, match="ordered by start_sec"):
        build_pitch_request([Note(62, 0.5, 0.2, "い"), Note(60, 0.0, 0.2, "あ")])


def test_negative_duration_is_rejected_by_contract():
    with pytest.raises(ValueError, match="end_sec"):
        build_pitch_request([Note(60, 1.0, -0.1, "あ")])


def test_resolver_errors_are_not_hidden():
    def fail(_lyric, _midi):
        raise RuntimeError("resolver failure")

    with pytest.raises(RuntimeError, match="resolver failure"):
        build_pitch_request([Note(60, 0.0, 0.2, "あ")], alias_resolver=fail)



def test_existing_oto_parser_adapter_uses_note_num_keyword():
    from axral_vocal_ai.adapters.vose import make_oto_alias_resolver

    class Parser:
        def __init__(self):
            self.calls = []

        def resolve_alias(self, lyric, prev_vowel=None, note_num=None):
            self.calls.append((lyric, prev_vowel, note_num))
            return OtoEntry(alias=lyric + "-resolved")

    parser = Parser()
    resolver = make_oto_alias_resolver(parser)
    request = build_pitch_request(
        [Note(64, 0.0, 0.3, "あ")],
        alias_resolver=resolver,
    )
    assert parser.calls == [("あ", None, 64)]
    assert request.notes[0].resolved_alias == "あ-resolved"
