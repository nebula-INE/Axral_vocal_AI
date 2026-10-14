# Japanese lyric normalization boundary

The experimental Japanese lyric normalizer provides a deterministic first step
before voicebank alias lookup or phoneme conversion. It:

- applies Unicode NFKC normalization and collapses whitespace;
- converts hiragana to katakana only when the token contains no CJK ideographs;
- preserves the original input for debugging and review;
- marks kanji-containing tokens as `needs_reading` rather than guessing a
  pronunciation;
- reports empty input explicitly.

This is **not** a Japanese tokenizer, pronunciation dictionary, G2P model, or
UTAU alias resolver. For example, the written form 明日は晴れ contains a
context-sensitive reading and a grammatical particle; blindly converting every
hiragana character to katakana would produce a misleading representation.
Such tokens must go through an explicit reading source or human review before
phoneme mapping.

## API

```python
from axral_vocal_ai.japanese_lyric import normalize_japanese_lyric

result = normalize_japanese_lyric("  みっくす  じゅーす ")
assert result.normalized == "ミックス ジュース"
assert result.status == "normalized"

result = normalize_japanese_lyric("明日は晴れ")
assert result.status == "needs_reading"
assert result.normalized == "明日は晴れ"
```

## Next steps before training

1. Add a versioned reading/phoneme mapping contract with explicit source and
   confidence metadata.
2. Resolve kana and phonemes against the actual voicebank alias inventory,
   without assuming every bank uses the same alias scheme.
3. Build reviewed examples covering kanji readings, okurigana, particles,
   long vowels, small kana, sokuon, mora boundaries, CV/VCV/CVVC aliases, and
   missing aliases.
4. Keep ambiguous cases out of automatic training labels until reviewed.
5. Evaluate by held-out voicebank and Japanese linguistic category.

The normalizer itself does not increase model quality or create training data;
it is a safe preprocessing boundary to make later language/phoneme handling
explicit and testable.
