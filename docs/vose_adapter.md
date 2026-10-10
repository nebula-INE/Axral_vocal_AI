# VO-SE_vocal request adapter

`axral_vocal_ai.adapters.vose.build_pitch_request` converts existing
`NoteEvent`-like data into a versioned `PitchRequest` snapshot.

- Times remain seconds; `end_sec = start_time + duration`.
- Original lyrics are retained. Alias resolution is opt-in and should call the
  existing VO-SE_vocal `OtoParser.resolve_alias(lyric, note_num=...)` rather
  than reimplementing UTAU alias or `prefix.map` rules.
- Unresolved non-rest lyrics remain `resolved_alias=None` and `voiced=None`.
  Known rest markers are marked unvoiced and are not sent to the resolver.
- The adapter does not sort notes or mutate source objects.
- Pitch automation is intentionally not mapped: VO-SE_vocal `PitchEvent.value`
  uses a distinct bend domain and must not be interpreted as semitones without
  an explicit, calibrated conversion policy.
- Resolved aliases only are exported; local WAV paths and `OtoEntry.wav_path`
  are never included in the request.

This adapter does not call synthesis, apply a pitch response, or alter the
production VO-SE_vocal renderer.
