from __future__ import annotations

import pytest

from axral_vocal_ai.japanese_lyric import normalize_japanese_lyric


def test_hiragana_is_normalized_to_katakana_and_original_is_preserved() -> None:
    result = normalize_japanese_lyric("  みっくす   じゅーす  ")
    assert result.original == "  みっくす   じゅーす  "
    assert result.normalized == "ミックス ジュース"
    assert result.status == "normalized"
    assert not result.contains_kanji
    assert result.warnings == ()


def test_nfkc_normalizes_full_width_latin_but_does_not_rewrite_it_as_phonemes() -> None:
    result = normalize_japanese_lyric("ＡＢＣ ｶﾅ")
    assert result.normalized == "ABC カナ"
    assert result.status == "normalized"


def test_kanji_is_preserved_and_flagged_for_reading_review() -> None:
    result = normalize_japanese_lyric("明日は晴れ")
    assert result.normalized == "明日ハ晴レ"
    assert result.status == "needs_reading"
    assert result.contains_kanji
    assert any("reading is unresolved" in warning for warning in result.warnings)


def test_empty_or_whitespace_input_is_explicitly_empty() -> None:
    for text in ("", "   ", "\n\t"):
        result = normalize_japanese_lyric(text)
        assert result.original == text
        assert result.normalized == ""
        assert result.status == "empty"
        assert result.warnings


def test_non_string_input_is_rejected() -> None:
    with pytest.raises(TypeError, match="lyric must be a string"):
        normalize_japanese_lyric(None)  # type: ignore[arg-type]


def test_kana_conversion_does_not_change_punctuation_or_latin_case() -> None:
    result = normalize_japanese_lyric("あ、Hello! んー")
    assert result.normalized == "ア、Hello! ンー"
