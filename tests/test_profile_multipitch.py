from axral_vocal_ai.voicebank.profile import build_voicebank_profile


class Entry:
    filename = "sample.wav"
    wav_path = "sample.wav"


class Parser:
    def all_aliases(self):
        return ["あ", "a い"]

    def get(self, alias):
        return Entry()

    def has_vcv(self):
        return True


def test_profile_records_explicit_multipitch_boundaries():
    profile = build_voicebank_profile(
        Parser(),
        pitch_bank_boundaries=(60.0, 72.0),
    )
    assert profile.pitch_bank_boundaries == (60.0, 72.0)
    assert "multipitch" in profile.format_hints
