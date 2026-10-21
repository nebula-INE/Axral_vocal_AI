# Pitch training candidate readiness gate

`src/axral_vocal_ai/pitch_training_readiness.py` provides
`assess_training_candidate(...)` for both existing schema families:

- `legacy-manifest-v1`
- `axral.pitch-training-example-1.0`

The function is metadata-only. It checks the quality report, split coverage,
voicebank-group coverage, source-origin classification, consent/permission,
and the presence of approved pitch labels. Synthetic fixtures, unknown source
origins, missing splits, invalid records, leakage, or unreviewed labels block
the candidate.

Use `dataset_origin="candidate_real_data"` only as a declaration that the
caller is assessing a real-data candidate. It is not evidence that the claim is
true. A successful result is only `candidate_for_human_training_review`; it
does not authorize training, certify rights, or verify the underlying source.
Human review of licensing, consent, provenance, label quality, and evaluation
isolation remains mandatory. `training_started` is always false.

Treat the legacy and example-level schemas independently. This gate does not
convert fields or units, load audio, start model training, or modify VO-SE_vocal.
