# Stratified pitch-delta evaluation

The experimental model currently predicts note-context pitch deltas, not audio.
This evaluator adds a reproducible report broken down by **voicebank** and
**MIDI pitch range**, because one aggregate score can hide poor performance on
a particular voicebank or register.

## Run

Use a manifest that passes the existing permissions, provenance, schema, and
voicebank-isolated split checks. The model argument can be either a raw model
artifact or the training report JSON:

```bash
python training/evaluate_pitch_model.py dataset/manifest.jsonl artifacts/pitch_delta_report.json --split validation --output artifacts/validation_metrics.json
python training/evaluate_pitch_model.py dataset/manifest.jsonl artifacts/pitch_delta_report.json --split test --output artifacts/final_test_metrics.json
```

The default split is `test`. Use `validation` during model development; only
evaluate the held-out test split after model/settings decisions are finalized.
The report includes a heuristic `label_quality_review` for the requested split
only, plus an `evaluation_scope` summary. A validation run does not emit test-split
metrics, test-split label-review flags, or the other splits' voicebank IDs and
record counts. The complete manifest is still validated for schema and split
isolation, but only a non-counting validation summary is included in the report.
The evaluator does not train, read audio, synthesize, or modify a project.

## Metrics

Each group reports example count, mean absolute error (MAE), root mean square
error (RMSE), and comparison with the zero-delta baseline. Positive MAE
improvement means the model beats predicting no correction; negative means it
does worse. Empty pitch bins are explicitly reported with zero examples and
null metrics rather than being mistaken for successful performance. The JSON
report includes split-scoped label-use counts and review flags, the sanitized
manifest-validation status, and output scope metadata alongside the metrics.

Pitch ranges are MIDI 0–47, 48–59, 60–71, 72–83, and 84–127. Voicebank groups
use the opaque `voicebank_id` from the validated manifest.

## Limitations

- These are label-space regression metrics, not audio or perceptual quality metrics.
- The manifest's group-split gate prevents one voicebank or source ID from
  crossing splits, but the dataset's correctness and licensing still require
  human review.
- Small sample counts can make group metrics unstable; always inspect counts.
- Do not tune on held-out test results. No result from this tool alone justifies
  automatic pitch edits or production-renderer integration.
