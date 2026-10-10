from dataclasses import dataclass

from axral_vocal_ai.voicebank.profile import build_voicebank_profile


@dataclass
class FakeEntry:
    filename: str
    wav_path: str


class FakeOtoParser:
    def __init__(self):
        self.entries = {
            "- あ": FakeEntry("a.wav", "/private/user/voice/a.wav"),
            "a い": FakeEntry("i.wav", "/private/user/voice/i.wav"),
            "D4/う": FakeEntry("u.wav", "/private/user/voice/D4/u.wav"),
        }

    def all_aliases(self):
        return list(self.entries)

    def get(self, alias):
        return self.entries.get(alias)

    def has_vcv(self):
        return True


def test_profile_summarizes_existing_parser_without_exporting_paths():
    profile = build_voicebank_profile(
        FakeOtoParser(),
        parser_version="test-parser",
    )

    assert profile.alias_count == 3
    assert profile.sample_count == 3
    assert profile.phoneme_inventory == ("あ", "い", "う")
    assert "vcv_aliases" in profile.format_hints
    assert "contextual_aliases" in profile.format_hints
    assert "folder_qualified_aliases" in profile.format_hints
    assert profile.parser_version == "test-parser"
    assert not any("/private/user" in item for item in profile.phoneme_inventory)
    assert not hasattr(profile, "wav_path")


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
