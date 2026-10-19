from pathlib import Path

import pytest

from axral_vocal_ai.oto_inventory import OtoEntry
from axral_vocal_ai.prefix_map import PrefixMapEntry
from axral_vocal_ai.voicebank_analysis import VoicebankAnalysis, VoicebankIssue
from axral_vocal_ai.wire_adapter import deterministic_wire_stub
from axral_vocal_ai.wire_request_builder import WireRequestBuildError, build_wire_request


def _analysis(tmp_path, *, entries=None, prefix_entries=(), issues=()):
    (tmp_path / "a.wav").write_bytes(b"metadata-only-test-file")
    if entries is None:
        entries = (OtoEntry(1, "a.wav", "あ", 0, 0, 0, 0, 0),)
    return VoicebankAnalysis(
        root=str(tmp_path), oto_files=("oto.ini",), prefix_map_files=("prefix.map",) if prefix_entries else (),
        entries=tuple(entries), prefix_entries=tuple(prefix_entries), duplicate_aliases=(),
        pattern_evidence=(), wav_files=(), issues=tuple(issues),
    )


def _notes():
    return [{"note_id": "n1", "midi_note": 60, "start_ms": 0, "duration_ms": 250,
             "alias": "あ", "lyric": "あ", "voiced": True}]


def test_builder_emits_valid_wire_metadata_without_absolute_sample_path(tmp_path):
    analysis = _analysis(tmp_path)
    request = build_wire_request(
        analysis, _notes(), profile_id="local-bank", profile_version="1", request_id="test-1"
    )
    assert request["contract"] == "axral.vocal-expression.request"
    assert request["schema_version"] == "1.0"
    assert request["notes"][0]["resolved_alias"] == "あ"
    assert request["notes"][0]["sample_ref"] == "voicebank://local-bank/a.wav"
    assert str(tmp_path) not in request["notes"][0]["sample_ref"]
    assert deterministic_wire_stub(request)["request_id"] == "test-1"


def test_builder_fails_closed_for_duplicate_aliases(tmp_path):
    entries = (
        OtoEntry(1, "a.wav", "あ", 0, 0, 0, 0, 0),
        OtoEntry(2, "a.wav", "あ", 0, 0, 0, 0, 0),
    )
    with pytest.raises(WireRequestBuildError, match="ambiguous") as exc:
        build_wire_request(_analysis(tmp_path, entries=entries), _notes(),
                           profile_id="bank", profile_version="1")
    assert exc.value.status == "needs_review"


def test_builder_fails_closed_for_duplicate_prefix_boundaries(tmp_path):
    mappings = (PrefixMapEntry(60, "A", ""), PrefixMapEntry(60, "B", ""))
    with pytest.raises(WireRequestBuildError, match="duplicate MIDI boundaries"):
        build_wire_request(_analysis(tmp_path, prefix_entries=mappings), _notes(),
                           profile_id="bank", profile_version="1")


def test_builder_rejects_nested_prefix_map_uncertainty(tmp_path):
    issue = VoicebankIssue("warning", "nested_prefix_map", "sub/prefix.map", None, "ambiguous")
    with pytest.raises(WireRequestBuildError, match="nested prefix.map"):
        build_wire_request(_analysis(tmp_path, issues=(issue,)), _notes(),
                           profile_id="bank", profile_version="1")


def test_builder_rejects_missing_alias_instead_of_guessing(tmp_path):
    notes = [{"note_id": "n1", "midi_note": 60, "start_ms": 0, "duration_ms": 250, "alias": "unknown"}]
    with pytest.raises(WireRequestBuildError, match="missing_alias") as exc:
        build_wire_request(_analysis(tmp_path), notes, profile_id="bank", profile_version="1")
    assert exc.value.status == "error"
