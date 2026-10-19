"""Conservative mora segmentation for explicitly supplied Japanese kana readings.

This is not a kanji reading resolver, G2P model, or UTAU alias resolver.
Unsupported characters are reported rather than silently discarded.
"""
from __future__ import annotations

from dataclasses import dataclass

from axral_vocal_ai.japanese_lyric import normalize_japanese_lyric


_SMALL_KANA = set("ァィゥェォャュョヮ")
_YOON_BASES = set("キギシジチヂニヒビピミリ")
_FOREIGN_BASES = {
    "イ": set("ェ"),
    "ウ": set("ァィェォ"),
    "ク": set("ァィェォ"),
    "グ": set("ァィェォ"),
    "シ": set("ェ"),
    "ジ": set("ェ"),
    "ス": set("ィェ"),
    "ズ": set("ィェ"),
    "ツ": set("ァィェォ"),
    "テ": set("ィュ"),
    "デ": set("ィュ"),
    "ト": set("ゥ"),
    "ド": set("ゥ"),
    "フ": set("ァィェォュ"),
    "ヴ": set("ァィェォ"),
}
_SEPARATORS = set(" \t\r\n、。，．・!?！？:：;；,.-—〜～「」『』（）()[]{}")


@dataclass(frozen=True)
class MoraSegmentation:
    """Auditable result of segmenting one explicitly provided reading."""

    original: str
    normalized: str
    morae: tuple[str, ...]
    status: str
    unresolved: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def segment_japanese_mora(text: str) -> MoraSegmentation:
    """Split kana readings into mora-like units without guessing pronunciations.

    Kanji-containing input is rejected for this stage until a reading is
    explicitly supplied. Small kana combine only with a conservative set of
    supported preceding kana; sokuon (ッ), moraic nasal (ン), and long-vowel
    mark (ー) remain individual units.
    """
    normalized_result = normalize_japanese_lyric(text)
    normalized = normalized_result.normalized
    if normalized_result.status == "empty":
        return MoraSegmentation(
            original=text,
            normalized=normalized,
            morae=(),
            status="empty",
            warnings=normalized_result.warnings,
        )
    if normalized_result.status == "needs_reading":
        return MoraSegmentation(
            original=text,
            normalized=normalized,
            morae=(),
            status="needs_reading",
            unresolved=tuple(char for char in normalized if ord(char) >= 0x3400 and ord(char) <= 0x3134F),
            warnings=normalized_result.warnings,
        )

    morae: list[str] = []
    unresolved: list[str] = []
    for char in normalized:
        if char in _SEPARATORS:
            continue
        if "ァ" <= char <= "ヶ" or char in {"ー", "ッ", "ン"}:
            if char in _SMALL_KANA:
                if not morae:
                    unresolved.append(char)
                    continue
                previous = morae[-1][-1]
                valid_yoon = char in "ャュョ" and previous in _YOON_BASES
                valid_foreign = char in "ァィゥェォュヮ" and char in _FOREIGN_BASES.get(previous, set())
                if valid_yoon or valid_foreign:
                    morae[-1] += char
                else:
                    unresolved.append(char)
                continue
            morae.append(char)
            continue
        unresolved.append(char)

    if unresolved:
        return MoraSegmentation(
            original=text,
            normalized=normalized,
            morae=tuple(morae),
            status="needs_review",
            unresolved=tuple(unresolved),
            warnings=("Some characters or small-kana combinations are unsupported; review before alias mapping.",),
        )
    return MoraSegmentation(
        original=text,
        normalized=normalized,
        morae=tuple(morae),
        status="segmented",
    )
