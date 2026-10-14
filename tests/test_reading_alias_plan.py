from __future__ import annotations

from pathlib import Path

from axral_vocal_ai.japanese_mora import segment_japanese_mora
from axral_vocal_ai.oto_inventory import OtoEntry
from axral_vocal_ai.prefix_map import PrefixMapEntry
from axral_vocal_ai.reading_alias_plan import plan_mora_aliases


def oto(line: int, filename: str, alias: str) -> OtoEntry:
    return OtoEntry(line, filename, alias, 0.0, 100.0, -100.0, 20.0, 10.0)


def test_plan_resolves_explicit_kana_reading_mora_by_mora() -> None:
    entries = [oto(1, "a.wav", "ア"), oto(2, "i.wav", "イ")]
    result = plan_mora_aliases("あい", [60, 64], entries)
    assert result.status == "resolved"
    assert result.morae == ("ア", "イ")
    assert [item.mapped_alias for item in result.resolutions] == ["ア", "イ"]


def test_prefix_map_is_applied_using_each_note_pitch() -> None:
    entries = [oto(1, "a.wav", "ア_low"), oto(2, "a-high.wav", "イ_high")]
    mappings = [
        PrefixMapEntry(boundary=0, prefix="", suffix="_low"),
        PrefixMapEntry(boundary=64, prefix="", suffix="_high"),
    ]
    result = plan_mora_aliases("あい", [60, 64], entries, mappings)
    assert result.status == "resolved"
    assert [item.mapped_alias for item in result.resolutions] == ["ア_low", "イ_high"]


def test_kanji_reading_is_not_guessed() -> None:
    result = plan_mora_aliases("明日", [60, 62], [oto(1, "a.wav", "ア")])
    assert result.status == "needs_reading"
    assert result.resolutions == ()
    assert result.warnings


def test_unsupported_mora_segmentation_does_not_emit_partial_plan() -> None:
    segmentation = segment_japanese_mora("ァ")
    assert segmentation.status == "needs_review"
    result = plan_mora_aliases("ァ", [60], [oto(1, "a.wav", "ァ")])
    assert result.status == "needs_review"
    assert result.resolutions == ()


def test_note_mora_count_mismatch_emits_no_partial_results() -> None:
    result = plan_mora_aliases("あい", [60], [oto(1, "a.wav", "ア")])
    assert result.status == "note_mora_count_mismatch"
    assert result.resolutions == ()


def test_missing_alias_is_reported_for_review() -> None:
    result = plan_mora_aliases("あい", [60, 61], [oto(1, "a.wav", "ア")])
    assert result.status == "needs_review"
    assert [item.status for item in result.resolutions] == ["resolved", "missing_alias"]


def test_voicebank_root_is_forwarded_to_alias_validation(tmp_path: Path) -> None:
    (tmp_path / "a.wav").write_bytes(b"placeholder")
    result = plan_mora_aliases("あ", [60], [oto(1, "a.wav", "ア")], voicebank_root=tmp_path)
    assert result.status == "resolved"
    assert result.resolutions[0].candidates[0].wav_path == (tmp_path / "a.wav").resolve()
