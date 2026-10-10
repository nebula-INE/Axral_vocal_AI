# Synthetic pitch baseline — Draft 1

## Purpose

Validate request/response wiring and evaluation math before importing real voicebanks or starting a Kaggle GPU session. This is a data-free engineering check, not evidence of singing quality or model generalization.

## Baseline

`axral_vocal_ai.baseline.zero_delta_baseline` emits a zero-semitone pitch delta at each supplied reference timestamp. It ignores target values by design. If there are no evaluation timestamps, it returns `no_change`.

The helper `mean_absolute_error` reports mean absolute error in semitones. To avoid silently comparing different time grids, it requires equal point counts and exact timestamp alignment.

## Synthetic fixture

Use hand-authored, deterministic labels such as:

| Time (s) | Reference delta (semitones) | Baseline prediction |
|---:|---:|---:|
| 0.00 | 0.00 | 0.00 |
| 0.10 | +0.25 | 0.00 |
| 0.20 | -0.50 | 0.00 |

Expected MAE: `(0.00 + 0.25 + 0.50) / 3 = 0.25` semitones.

These numbers are test fixtures only. They are not derived from a voicebank, an audio recording, or a claim about natural pitch behavior.

## Guardrails

- No audio, user projects, voicebank samples, network access, or model weights are required.
- Do not use this baseline as an automatic correction system.
- Do not connect it to the production renderer or write its output into original pitch automation.
- This baseline only validates the evaluation plumbing. Before a learned model, define target-label provenance, allowed data use, split by whole voicebank, and meaningful metrics.
- The exact timestamp requirement is intentionally strict; if later evaluation uses resampling/interpolation, define and test that policy explicitly instead of silently matching nearest points.
