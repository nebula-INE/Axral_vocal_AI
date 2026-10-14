# UTAU alias resolution integration

`axral_vocal_ai.voicebank_alias.resolve_utau_alias` connects the parsed
`prefix.map` mapping to the `oto.ini` metadata inventory.

## Behavior

- Applies the note-boundary prefix/suffix mapping before looking up the alias.
- Preserves duplicate aliases and returns `ambiguous`; it never chooses a
  sample arbitrarily.
- Optionally validates WAV paths against a supplied voicebank root, including
  traversal/absolute-path rejection and existence checks.
- Reports missing aliases and invalid sample paths explicitly.

## Example

```python
from axral_vocal_ai.voicebank_alias import resolve_utau_alias

result = resolve_utau_alias("あ", 65, oto_entries, prefix_entries, voicebank_root)
if result.status == "resolved":
    candidate = result.candidates[0]
    # Pass candidate.entry/candidate.wav_path to a separately reviewed renderer.
elif result.status == "ambiguous":
    # Ask the caller to apply a voicebank-specific policy; do not guess.
    ...
```

This is metadata/path resolution only. It does not decode WAV data, infer
CV/VCV/CVVC transitions, select timing windows, or render audio. Those require
separate tests against legally usable real voicebanks and the VO-SE_vocal
renderer.
