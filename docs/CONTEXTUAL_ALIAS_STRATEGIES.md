# Context-aware UTAU alias strategies

The contextual planner adds an explicit strategy layer above mora segmentation
and the alias inventory. It does not infer a voicebank's alias convention,
decode WAV files, synthesize audio, or replace the baseline reading planner.

## Configure the voicebank convention

- **CV**: one configured alias template per mora.
- **VCV**: an initial-note template plus a configured transition template.
  Every preceding mora used for context must have an explicit entry in
  vowel_map; the planner never guesses vowel identity.
- **CVVC**: an initial-note template, then two independent lookups per later
  note: onset (CV) and vowel-to-consonant transition (VC). Both templates are
  configurable because CVVC spelling conventions vary.

Templates support {current} and {previous_vowel}. For example,
"{previous_vowel} {current}" can be used by a bank with that spelling convention.
This is an example, not a universal UTAU rule.

## Review behavior

- Input is already segmented morae; kanji readings and phoneme conversion are
  outside this layer.
- One mora is aligned to one MIDI note. A count mismatch returns no lookups.
- Missing vowel mappings return needs_review with no partial lookups.
- Missing and duplicate aliases remain visible; ambiguous entries are never
  silently selected.
- Prefix mapping and optional WAV path validation use the existing resolver.
- A successful metadata lookup does not prove acoustic validity or naturalness.
  CVVC onset/transition timing and sample slicing remain future work.
