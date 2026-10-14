# Pitch-curve diagnostics

The experimental inference path can produce multiple pitch-delta proposals within
a note. Before considering any integration, use `audit_pitch_curve` to summarize
adjacent changes and flag unusually large jumps or steep slopes for review.

```python
from axral_vocal_ai.curve_diagnostics import audit_pitch_curve

report = audit_pitch_curve([
    {"time_sec": 0.00, "delta_semitones": 0.0},
    {"time_sec": 0.05, "delta_semitones": 0.1},
    {"time_sec": 0.10, "delta_semitones": 0.2},
])
```

The defaults flag a segment when its absolute delta change exceeds 1.0 semitone
or its absolute slope exceeds 12 semitones per second. Pass thresholds explicitly
for experiments; these are review heuristics, not universal musical or perceptual
limits.

**Important:** pass points for one note only, in chronological order. Do not
measure across note boundaries, where intended pitch transitions can create
misleading jumps. The function reports metrics only; it does not smooth, clamp,
reject, or alter any proposal. Tests on synthetic values establish calculation
behavior, not that a model sounds natural. Evaluation on held-out, rights-cleared
real data and listening tests remain necessary before renderer integration.
