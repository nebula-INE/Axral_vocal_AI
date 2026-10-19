"""End-to-end metadata contract test; deliberately does not render audio."""

from axral_vocal_ai.oto_inventory import OtoEntry
from axral_vocal_ai.voicebank_analysis import VoicebankAnalysis
from axral_vocal_ai.wire_adapter import adapt_wire_response, deterministic_wire_stub
from axral_vocal_ai.wire_request_builder import build_wire_request


def test_analysis_to_wire_stub_to_internal_proposal_is_non_destructive(tmp_path):
    # The file is only a path fixture; no WAV decoding or audio processing occurs.
    (tmp_path / "a.wav").write_bytes(b"metadata-only-test-file")
    analysis = VoicebankAnalysis(
        root=str(tmp_path),
        oto_files=("oto.ini",),
        prefix_map_files=(),
        entries=(OtoEntry(1, "a.wav", "あ", 0, 0, 0, 0, 0),),
        prefix_entries=(),
        duplicate_aliases=(),
        pattern_evidence=(),
        wav_files=(),
        issues=(),
    )
    notes = [{
        "note_id": "note-1",
        "midi_note": 60,
        "start_ms": 0.0,
        "duration_ms": 250.0,
        "alias": "あ",
        "lyric": "あ",
        "voiced": True,
    }]

    request = build_wire_request(
        analysis,
        notes,
        profile_id="local-bank",
        profile_version="1",
        request_id="pipeline-test-1",
    )
    response = deterministic_wire_stub(request)
    proposal = adapt_wire_response(request, response)

    assert request["notes"][0]["sample_ref"] == "voicebank://local-bank/a.wav"
    assert proposal.status == "no_change"
    assert proposal.pitch_deltas == ()
    # The input note metadata remains untouched by building/adapting the proposal.
    assert notes == [{
        "note_id": "note-1",
        "midi_note": 60,
        "start_ms": 0.0,
        "duration_ms": 250.0,
        "alias": "あ",
        "lyric": "あ",
        "voiced": True,
    }]
