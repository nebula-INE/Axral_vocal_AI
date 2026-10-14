from __future__ import annotations

import pytest

from axral_vocal_ai.japanese_mora import segment_japanese_mora


def test_segments_basic_kana_and_preserves_order() -> None:
    result = segment_japanese_mora("さくら")
    assert result.status == "segmented"
    assert result.morae == ("サ", "ク", "ラ")


def test_combines_yoon_into_one_mora() -> None:
    assert segment_japanese_mora("きゃりー").morae == ("キャ", "リ", "ー")


def test_sokuon_and_moraic_nasal_are_explicit_units() -> None:
    assert segment_japanese_mora("がっこう").morae == ("ガ", "ッ", "コ", "ウ")


def test_supported_foreign_sound_combination() -> None:
    assert segment_japanese_mora("ふぁいる").morae == ("ファ", "イ", "ル")


def test_kanji_requires_explicit_reading() -> None:
    result = segment_japanese_mora("明日は晴れ")
    assert result.status == "needs_reading"
    assert result.morae == ()
    assert result.unresolved


def test_orphan_small_kana_is_not_silently_dropped() -> None:
    result = segment_japanese_mora("ゃ")
    assert result.status == "needs_review"
    assert result.unresolved == ("ャ",)


def test_unsupported_latin_is_reported() -> None:
    result = segment_japanese_mora("hello")
    assert result.status == "needs_review"
    assert result.unresolved


def test_empty_input() -> None:
    result = segment_japanese_mora("  ")
    assert result.status == "empty"
    assert result.morae == ()


def test_non_string_input_raises_type_error() -> None:
    with pytest.raises(TypeError):
        segment_japanese_mora(None)  # type: ignore[arg-type]
