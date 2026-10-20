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


@pytest.mark.parametrize("profile_id", [
    "../other", "bank/child", r"bank\\child", "bank?query", "bank#fragment",
    "white space", ".", "..", "",
])
def test_builder_rejects_unsafe_profile_id_in_sample_uri(tmp_path, profile_id):
    with pytest.raises(WireRequestBuildError, match="profile_id"):
        build_wire_request(
            _analysis(tmp_path), _notes(), profile_id=profile_id, profile_version="1"
        )


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


@pytest.mark.parametrize("unsafe_path", [
    "/tmp/a.wav", "../a.wav", "sub/../../a.wav", r"C:\\voicebank\\a.wav",
    r"sub\\a.wav", r"\\\\server\\share\\a.wav",
])
def test_builder_rejects_absolute_or_traversing_sample_paths(tmp_path, unsafe_path):
    entry = OtoEntry(1, unsafe_path, "あ", 0, 0, 0, 0, 0)
    # The analysis resolver can reject unsafe paths before the wire builder's
    # own relative-path guard runs. Both paths must fail closed.
    with pytest.raises(WireRequestBuildError, match="invalid_sample_path|safe voicebank-relative path"):
        build_wire_request(_analysis(tmp_path, entries=(entry,)), _notes(),
                           profile_id="bank", profile_version="1")


@pytest.mark.parametrize("field,value", [
    ("start_ms", float("nan")), ("start_ms", -1), ("duration_ms", float("inf")),
    ("duration_ms", True), ("voiced", "yes"), ("lyric", 3),
])
def test_builder_rejects_malformed_note_metadata(tmp_path, field, value):
    notes = _notes()
    notes[0][field] = value
    with pytest.raises(WireRequestBuildError):
        build_wire_request(_analysis(tmp_path), notes, profile_id="bank", profile_version="1")


@pytest.mark.parametrize("baseline_pitch", [
    "not-a-list",
    [{"time_ms": float("nan"), "hz": 440}],
    [{"time_ms": 0, "hz": float("inf")}],
    [{"time_ms": -1, "hz": 440}],
    [{"time_ms": 251, "hz": 440}],
    [{"time_ms": 20, "hz": 440}, {"time_ms": 10, "hz": 450}],
    [{"time_ms": 0, "hz": 0}],
    [{"time_ms": True, "hz": 440}],
])
def test_builder_rejects_invalid_baseline_pitch(tmp_path, baseline_pitch):
    notes = _notes()
    notes[0]["baseline_pitch"] = baseline_pitch
    with pytest.raises(WireRequestBuildError, match="baseline_pitch"):
        build_wire_request(
            _analysis(tmp_path), notes, profile_id="bank", profile_version="1"
        )


def test_builder_copies_valid_baseline_pitch_without_mutating_input(tmp_path):
    notes = _notes()
    baseline = [{"time_ms": 0, "hz": 261.6256}, {"time_ms": 250, "hz": 261.6256}]
    notes[0]["baseline_pitch"] = baseline
    request = build_wire_request(
        _analysis(tmp_path), notes, profile_id="bank", profile_version="1"
    )
    assert request["notes"][0]["baseline_pitch"] == [
        {"time_ms": 0.0, "hz": 261.6256},
        {"time_ms": 250.0, "hz": 261.6256},
    ]
    assert baseline == [{"time_ms": 0, "hz": 261.6256}, {"time_ms": 250, "hz": 261.6256}]


def test_builder_rejects_duplicate_note_ids_and_blank_request_id(tmp_path):
    notes = _notes() * 2
    with pytest.raises(WireRequestBuildError, match="duplicate note_id"):
        build_wire_request(_analysis(tmp_path), notes, profile_id="bank", profile_version="1")
    with pytest.raises(WireRequestBuildError, match="request_id"):
        build_wire_request(_analysis(tmp_path), _notes(), profile_id="bank",
                           profile_version="1", request_id=" ")
