from dataclasses import dataclass

from axral_vocal_ai.voicebank.profile import build_voicebank_profile


@dataclass
class FakeEntry:
    filename: str | None = None
    wav_path: str | None = None


class FakeOtoParser:
    def __init__(self, voice_dir):
        # Files are real test fixtures so sample_count can mean resolved,
        # existing audio files rather than just aliases or candidate paths.
        (voice_dir / "a.wav").write_bytes(b"RIFF")
        (voice_dir / "i.wav").write_bytes(b"RIFF")
        nested = voice_dir / "subdir" / "D4"
        nested.mkdir(parents=True)
        (nested / "u.wav").write_bytes(b"RIFF")
        missing = voice_dir / "missing.wav"
        self.entries = {
            # CV-style alias
            "あ": FakeEntry("a.wav", str(voice_dir / "a.wav")),
            # VCV-style alias
            "a い": FakeEntry("i.wav", str(voice_dir / "i.wav")),
            # Nested oto.ini / folder-qualified alias shape
            "subdir/D4/う": FakeEntry("u.wav", str(nested / "u.wav")),
            # A second alias referencing the same physical sample
            "う_alt": FakeEntry("u.wav", str(nested / "u.wav")),
            # Alias exists but its candidate WAV file is missing
            "え": FakeEntry("missing.wav", str(missing)),
        }

    def all_aliases(self):
        return list(self.entries)

    def get(self, alias):
        return self.entries.get(alias)

    def has_vcv(self):
        return True


def test_profile_summarizes_existing_parser_without_exporting_paths(tmp_path):
    profile = build_voicebank_profile(
        FakeOtoParser(tmp_path),
        parser_version="test-parser",
        # CVVC is supplied as a parser/audit hint, not guessed from alias text.
        format_hints=("cv_aliases", "cvvc_aliases", "prefix_map"),
        pitch_bank_boundaries=(60.0, 72.0),
    )

    assert profile.alias_count == 5
    # Duplicate aliases for one physical sample are deduplicated. The missing
    # WAV candidate for "え" is not counted.
    assert profile.sample_count == 3
    assert profile.phoneme_inventory == ("あ", "い", "う", "う_alt", "え")
    assert "vcv_aliases" in profile.format_hints
    assert "cv_aliases" in profile.format_hints
    assert "cvvc_aliases" in profile.format_hints
    assert "prefix_map" in profile.format_hints
    assert "contextual_aliases" in profile.format_hints
    assert "folder_qualified_aliases" in profile.format_hints
    assert "multipitch" in profile.format_hints
    assert profile.pitch_bank_boundaries == (60.0, 72.0)
    assert profile.parser_version == "test-parser"
    assert not any(str(tmp_path) in item for item in profile.phoneme_inventory)
    assert not hasattr(profile, "wav_path")


def test_profile_does_not_count_entry_without_any_sample_reference(tmp_path):
    class Parser:
        def all_aliases(self):
            return ["か"]

        def get(self, alias):
            return FakeEntry()

        def has_vcv(self):
            return False

    profile = build_voicebank_profile(Parser())
    assert profile.alias_count == 1
    assert profile.sample_count == 0


def test_profile_handles_empty_voicebank():
    class EmptyParser:
        def all_aliases(self):
            return []

        def get(self, alias):
            return None

        def has_vcv(self):
            return False

    profile = build_voicebank_profile(EmptyParser())
    assert profile.alias_count == 0
    assert profile.sample_count == 0
    assert profile.phoneme_inventory == ()


def test_profile_does_not_count_missing_wav_even_if_entry_has_candidate_path(tmp_path):
    class Parser:
        def all_aliases(self):
            return ["missing"]

        def get(self, alias):
            return FakeEntry("missing.wav", str(tmp_path / "does-not-exist.wav"))

        def has_vcv(self):
            return False

    profile = build_voicebank_profile(Parser())
    assert profile.alias_count == 1
    assert profile.sample_count == 0
