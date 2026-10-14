# Japanese kana-to-mora segmentation

`axral_vocal_ai.japanese_mora.segment_japanese_mora` is a deterministic,
conservative next step after Unicode/lyric normalization.

## Example

```python
from axral_vocal_ai.japanese_mora import segment_japanese_mora

result = segment_japanese_mora("きゃりー")
assert result.morae == ("キャ", "リ", "ー")
assert result.status == "segmented"
```

## Safety and scope

- Kanji-containing text returns `needs_reading`; this function never guesses a
  reading. Supply a human-reviewed kana reading before segmentation.
- Small kana combine only for explicitly supported combinations. Unsupported
  characters and combinations are returned in `unresolved` with
  `needs_review`; they are not silently discarded.
- `ッ`, `ン`, and `ー` remain explicit units so a later language/voicebank
  adapter can apply its own timing and alias rules.
- This output is a mora-like linguistic representation, **not** UTAU CV/VCV/CVVC
  aliases, phoneme IDs, timing, pitch, or rendered audio.
- Real voicebank coverage must be measured against reviewed readings and
  held-out voicebanks before this can be used for production synthesis.

## Next integration work

1. Add reviewed reading input and provenance (manual/dictionary/model).
2. Build an alias inventory adapter for UTAU `oto.ini`, prefix maps, and CV/VCV/CVVC.
3. Evaluate unresolved rates and alias coverage across legally usable voicebanks.
