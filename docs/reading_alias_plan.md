# Explicit Japanese reading to UTAU alias plan

`axral_vocal_ai.reading_alias_plan.plan_mora_aliases` connects the existing
kana normalizer, conservative mora segmenter, pitch-aware `prefix.map` mapper,
and `oto.ini` alias inventory.

## Contract

- Input must be an explicitly supplied kana reading. Kanji readings are not
  guessed; unresolved input returns without creating a partial plan.
- The baseline assumes exactly one note per mora. A count mismatch is reported
  before any aliases are resolved.
- Each mora is looked up at its own MIDI note number, so pitch-dependent prefix
  and suffix mappings can differ within a phrase.
- Missing aliases, duplicate aliases, and invalid sample paths remain visible
  through each `AliasResolution`; unresolved results make the plan
  `needs_review`.
- An optional voicebank root enables file-existence and path-containment checks.

## Deliberate limits

This is a conservative CV-style baseline, not a complete UTAU lyric-to-phoneme
engine. It does not infer kanji readings, note-to-mora alignment for melisma,
CV/VCV/CVVC transitions, consonant timing, or acoustic quality. Do not feed
unreviewed results into training labels or production rendering. Those next
steps need voicebank-specific policy and tests against legally usable banks
while keeping VO-SE_vocal as the renderer of record.
