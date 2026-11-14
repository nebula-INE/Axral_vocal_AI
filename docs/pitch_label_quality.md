# Pitch-label quality review

## Run the combined dataset audit

The dataset audit CLI first validates the manifest schema, permissions, provenance,
and split isolation. If that gate passes, it emits both dataset readiness statistics
and the heuristic label-review report in one JSON document:

```bash
python training/audit_pitch_dataset.py dataset/manifest.jsonl
python training/audit_pitch_dataset.py dataset/manifest.jsonl --output artifacts/dataset_readiness.json
```

The combined report has two relevant sections:

- `by_split`, `by_voicebank`, and `by_midi_range`: usable-label counts, coverage,
  and pitch-delta distributions.
- `label_quality_review`: label mapping, near-boundary targets, and unusual
  adjacent changes that should be inspected by a human.

The Python API is also available for a metadata-only review pass:

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
valid under the annotation convention. Inspect source/provenance and annotation
policy before changing any labels. The audit does not read audio, assess
naturalness, train a model, or modify the manifest.

Default thresholds are configurable heuristics (1 semitone adjacent jump,
12 semitones/second slope, 0.05 semitone boundary margin). Use held-out voicebanks
and independently reviewed, rights-cleared labels for model evaluation; do not
use this report alone to claim model quality.
