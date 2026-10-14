"""Deterministic Japanese lyric normalization before phoneme/alias mapping.

This module deliberately does not guess readings or produce phonemes. Kanji and
other unresolved characters are surfaced for a later reading/phoneme resolver.
"""
from __future__ import annotations

from dataclasses import dataclass
import unicodedata


@dataclass(frozen=True)
class LyricNormalization:
    """Loss-aware result of normalizing one lyric token."""

    original: str
    normalized: str
    status: str
    contains_kanji: bool
    warnings: tuple[str, ...] = ()


def _is_cjk_ideograph(char: str) -> bool:
    codepoint = ord(char)
    return (
        0x3400 <= codepoint <= 0x4DBF
        or 0x4E00 <= codepoint <= 0x9FFF
        or 0xF900 <= codepoint <= 0xFAFF
        or 0x20000 <= codepoint <= 0x3134F
    )


def _hiragana_to_katakana(text: str) -> str:
    """Convert standard hiragana code points to katakana, preserving other text."""
    result: list[str] = []
    for char in text:
        codepoint = ord(char)
        # U+3041..U+3096 have direct katakana counterparts at +0x60.
        if 0x3041 <= codepoint <= 0x3096:
            result.append(chr(codepoint + 0x60))
        else:
            result.append(char)
    return "".join(result)


def normalize_japanese_lyric(text: str) -> LyricNormalization:
    """Normalize Unicode/spacing and kana script without inventing a reading.

    NFKC handles compatibility forms (for example, full-width Latin letters).
    Hiragana is converted to katakana to establish a stable kana representation.
    Original input is always retained. Kanji triggers needs_reading because its
    pronunciation cannot safely be inferred from the written form alone.
    """
    if not isinstance(text, str):
        raise TypeError("lyric must be a string")

    normalized = unicodedata.normalize("NFKC", text)
    normalized = " ".join(normalized.split())
    contains_kanji = any(_is_cjk_ideograph(char) for char in normalized)
    # Converting kana inside kanji-containing text can corrupt lexical readings
    # (for example, the particle は in 明日は晴れ). Defer that whole token to
    # reading resolution instead of making a misleading partial conversion.
    if not contains_kanji:
        normalized = _hiragana_to_katakana(normalized)

    if not normalized:
        return LyricNormalization(
            original=text,
            normalized="",
            status="empty",
            contains_kanji=False,
            warnings=("Lyric is empty after Unicode and whitespace normalization.",),
        )

    warnings: list[str] = []
    if contains_kanji:
        warnings.append(
            "Kanji reading is unresolved; supply or review a reading before phoneme mapping."
        )

    return LyricNormalization(
        original=text,
        normalized=normalized,
        status="needs_reading" if contains_kanji else "normalized",
        contains_kanji=contains_kanji,
        warnings=tuple(warnings),
    )
