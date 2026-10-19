# Pitch dataset readiness audit

Run the metadata-only audit before training to check whether the current labels
are usable and how they are distributed:

```bash
python training/audit_pitch_dataset.py dataset/manifest.jsonl
python training/audit_pitch_dataset.py dataset/manifest.jsonl --output artifacts/dataset_readiness.json
```

The CLI first runs the existing manifest gate for schema, approved permissions,
provenance, label bounds, and voicebank/source split isolation. It then reports:

- raw target points versus labels mapped to an unambiguous voiced note;
- overall and per-split label coverage;
- mean, median, minimum, and maximum target delta, plus zero/non-zero counts;
- usable label counts by voicebank and MIDI range.

Coverage only measures whether a target point can be associated with a voiced
note under the current interval rules. It does **not** certify that the label is
correct, that the source is legally usable beyond the recorded review, or that
a resulting singing voice sounds natural. The report does not load audio, train
a model, or change project/rendering behavior. Synthetic tests verify report
accounting only; run this audit on a genuinely approved manifest before drawing
dataset-quality conclusions.
