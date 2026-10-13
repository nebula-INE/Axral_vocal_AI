# Per-note pitch-curve evaluation

The experimental runtime exposes `predict_curve(request, samples_per_note=9)`.
It samples the existing model at evenly spaced phases strictly inside each
eligible note. The legacy `predict()` API remains sparse and unchanged in
behavior. Curve sampling retains zero-valued points because dropping them would
distort the observed spacing and make adjacent-jump/slope metrics misleading.

Use `audit_pitch_response_curves(request, response)` to validate the response
against the request and report discontinuity metrics independently for each note:

```python
from axral_vocal_ai.curve_evaluation import audit_pitch_response_curves

response = runtime.predict_curve(request, samples_per_note=9)
report = audit_pitch_response_curves(request, response)
```

Notes that are rests, have zero duration, or overlap another interval are not
audited. Points must map to exactly one eligible note interior. This prevents a
legitimate transition between notes from being counted as an intra-note jump.

The report's thresholds are configurable review heuristics, not perceptual
standards. This stage does not read audio, compare against ground-truth pitch,
train a model, smooth or alter output, write projects, or call the production
renderer. Synthetic tests verify API behavior and arithmetic only. Before any
renderer integration, evaluate on rights-cleared real recordings, compare with
the zero-delta baseline and held-out voicebanks, inspect label quality, and run
blinded listening tests.
