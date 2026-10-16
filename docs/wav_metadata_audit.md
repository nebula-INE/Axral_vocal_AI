# WAV metadata audit

`axral_vocal_ai.wav_metadata.inspect_wav(path)` reads RIFF/WAVE chunk metadata
for a local UTAU sample. It does not decode samples or change files.

The report includes format code, channel count, sample rate, bit depth, byte
rate, block alignment, data-chunk size, and a duration estimate. Structural
problems raise `ValueError`; suspicious sizes and frame alignment are returned
as explicit issue codes. Unsupported compression formats are named but are not
declared renderable.

This is an initial structural check, not acoustic validation: it cannot prove
that the sample contains the expected phoneme, is non-silent, or sounds correct.
The audit is intentionally independent of the voicebank scanner so the next
integration step can add per-entry diagnostics without changing the current
versioned report schema.
