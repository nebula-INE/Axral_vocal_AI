# UTAU oto.ini alias inventory

The function axral_vocal_ai.oto_inventory.parse_oto_ini parses standard
six-field records into metadata and returns line-level issues for malformed
records.

## Example

    from axral_vocal_ai.oto_inventory import parse_oto_ini

    result = parse_oto_ini("あ.wav=あ,0,100,-100,20,10")
    for entry in result.entries:
        print(entry.alias, entry.wav_filename, entry.preutterance)
    for issue in result.issues:
        print(issue.line_number, issue.message)

## Compatibility and safety boundaries

- Duplicate aliases are preserved in source order; no arbitrary "first wins"
  policy is imposed.
- Backslashes in relative WAV paths are normalized to forward slashes. Absolute
  paths remain explicit and should be validated against the voicebank root by a
  later filesystem-aware layer.
- Invalid, missing, or non-finite numeric fields are reported as issues rather
  than silently coerced.
- This is metadata parsing only. It does not verify that files exist, decode WAV
  audio, apply prefix.map, infer CV/VCV/CVVC transitions, or render sound.
- Consumers must validate paths before opening files and evaluate alias coverage
  against actual voicebanks.
