# Proposal-only pitch-delta inference runtime

This runtime is the first file-backed inference boundary for the experimental
linear pitch-delta model. It is a plumbing milestone, **not** evidence of musical
quality and not a production integration.

## Load a model

Install the package and its runtime dependency:

```bash
python -m pip install -e .
```

The loader accepts either a raw model artifact (the `model` object emitted by
training) or the full training report emitted by
`training/train_pitch_model.py`. A report wrapper must have
`status: experimental_training_complete`. Schema, feature names/version,
target kind, safety metadata, weight count, and finite numeric weights are
validated before use.

```python
from axral_vocal_ai.contracts import PitchNote, PitchRequest
from axral_vocal_ai.inference import PitchDeltaInferenceRuntime

runtime = PitchDeltaInferenceRuntime.from_file("artifacts/pitch_delta_report.json")
request = PitchRequest(
    request_id="preview-001",
    notes=(
        PitchNote(start_sec=0.0, end_sec=0.8, midi_note=60, lyric="a"),
        PitchNote(start_sec=0.8, end_sec=1.6, midi_note=62, lyric="i"),
    ),
)
response = runtime.predict(request)
```

## Output behavior

- The runtime proposes at most one point at the midpoint of each unambiguous,
  non-zero-duration voiced note.
- Explicitly unvoiced notes are skipped. Overlapping note intervals are skipped
  rather than guessing which note owns a proposal.
- Zero-valued predictions are omitted. If there are no proposals, the response
  status is `no_change`.
- Every non-zero output is checked by the existing response validation gate and
  stays within the experimental +/-2-semitone bound.
- The request correlation ID is preserved in the response.

## Hard limits

- The runtime reads JSON model metadata only; it does not read audio.
- It does not write to UST/project files, edit pitch curves, call a renderer, or
  synthesize waveforms.
- The current feature set is intentionally small and ignores lyric/phoneme
  context. Midpoint-only output is a technical smoke-test API, not a complete
  singing-expression curve.
- Synthetic CI fixtures validate loading and API behavior only. Real, rights-
  cleared data, held-out voicebank evaluation, and listening tests are still
  required before claiming musical usefulness.
