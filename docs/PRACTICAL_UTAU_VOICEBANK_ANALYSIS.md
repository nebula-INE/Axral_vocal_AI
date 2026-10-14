# Practical UTAU voicebank analysis

`axral_vocal_ai.voicebank_analysis.analyze_voicebank(root)` performs a first-pass, read-only scan of a local voicebank directory.

```python
from axral_vocal_ai.voicebank_analysis import analyze_voicebank

report = analyze_voicebank("/path/to/voicebank")
print(report.to_json())
print(report.summary)
```

## Checks performed

- Recursively finds `oto.ini` and `prefix.map` (case-insensitive filenames).
- Reads UTF-8/UTF-8-BOM and common Japanese Windows CP932 text.
- Parses records using the existing conservative parsers and retains line-level issues.
- Rebases nested `oto.ini` WAV paths relative to the scanned voicebank root.
- Checks WAV existence, absolute paths, directory traversal, and resolved paths escaping the root.
- Preserves duplicate aliases and reports every duplicate group.
- Reports alias spelling-shape counts as evidence only; it does not automatically label a bank CV/VCV/CVVC because alias spelling varies.
- Emits a versioned JSON-ready report and a compact summary.

## Important boundaries

This is a metadata and filesystem audit, not a WAV decoder or acoustic quality test. It does not infer kanji readings, guarantee that a WAV contains the expected phoneme, measure sample quality, infer reliable CV/VCV/CVVC conventions, implement CVVC timing/sample slicing, or render audio. A clean report means the inventory is structurally plausible, not that every note will sound correct. Test with a permitted real voicebank and compare rendered output against expected notes before production use.

The scanner reads local files only and does not upload or copy voicebank audio into the repository. Do not commit copyrighted or restricted voicebank data.
