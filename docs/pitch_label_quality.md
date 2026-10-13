# Pitch-label quality review

Run the metadata-only review-flag pass after the manifest passes the existing
schema, permissions, provenance, and split-isolation gate:

```python
from axral_vocal_ai.label_quality import audit_label_quality

report = audit_label_quality(validated_records)
```

The report highlights:
- labels not strictly inside exactly one eligible voiced, non-overlapping note;
- labels close to the experimental +/-2-semitone bound;
- large adjacent changes or steep slopes between consecutive labels mapped to
  the same note.

These are **human-review prompts**, not automatic label rejection. Strong pitch
changes can be musically intentional, and labels near the output bound may be
valid under the annotation convention. Inspect the source/provenance and
annotation policy before changing any labels. The audit does not read audio,
assess naturalness, train a model, or modify the manifest.

Default thresholds are deliberately configurable heuristics (1 semitone
adjacent jump, 12 semitones/second slope, 0.05 semitone boundary margin). Use
held-out voicebanks and independently reviewed, rights-cleared labels for model
evaluation; do not use this report alone to claim model quality.
