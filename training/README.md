# Training workspace (Kaggle-first proposal)

Kaggle is the initial hosted experiment environment, not a permanent production dependency. Use it for reproducible small experiments after the data and target are defined. Do not start expensive GPU sessions until a baseline and evaluation split exist.

## Notebook workflow

1. Keep notebooks in a separate private Kaggle notebook or private dataset while data rights and contents are being reviewed.
2. Record dataset source, license/permission, allowed uses, attribution requirements, and any restrictions before importing data.
3. Start with a CPU-only data audit and a tiny synthetic dataset to validate preprocessing and metrics. The repository now has a data-free zero-delta baseline and synthetic metric fixture in `docs/synthetic_baseline.md`.
4. Split train/validation/test by voicebank where the dataset permits. Keep at least one voicebank entirely out of training for a generalization check.
5. Run a small baseline first; record GPU type, package versions, random seed, data version, run configuration, duration, peak memory, and metrics.
6. Only then compare GPU settings or expand the training corpus.
7. Export model weights and a manifest containing model version, contract schema version, training data identifiers, preprocessing version, metrics, and known limitations.
8. Download only artifacts that are allowed to be redistributed. Never commit private datasets, voicebank WAVs, Kaggle credentials, notebook secrets, or large checkpoints to this repository.

## Initial MVP

The first model target is a non-destructive pitch-expression proposal, not waveform generation. The first milestone is to validate the data pipeline and evaluation using a deterministic baseline or small toy model. The baseline is an engineering reference, not evidence of naturalness or model quality. A learned model should not be trained until target labels, permitted data, and success criteria are explicit.

## Required evaluation

- Compare against a no-AI baseline.
- Report error in semitones and continuity/smoothness metrics where appropriate.
- Check behavior on voicebanks excluded from training.
- Ensure output times are ordered and finite, deltas are bounded by an explicit policy, and unvoiced regions are not modified.
- Treat subjective listening and existing VO-SE_vocal render regression checks as required before integration.

## Reproducibility record

For each run, save a human-readable record of:
- dataset identifiers and permission status (no private content),
- train/validation/test split by voicebank,
- preprocessing and label definitions,
- seed and configuration,
- environment/package versions and accelerator,
- baseline and model metrics,
- artifact checksum and schema version.

Do not upload copyrighted or restricted data to Kaggle merely because the platform supports private datasets. Confirm that the applicable license and consent permit hosted processing.


## Implemented first gate: metadata manifest validation

The repository now includes `training/validate_dataset.py` and
`axral_vocal_ai.training_data`. Validate a JSONL manifest after installing the
package with `python -m pip install -e ".[dev]"`:

```bash
python training/validate_dataset.py path/to/manifest.jsonl
python training/validate_dataset.py path/to/manifest.jsonl --require-labeled
```

The first command checks the metadata schema and permission gate. The second
also requires a non-empty pitch-delta target on every record and is the stricter
pre-training readiness check. Both commands reject non-approved sources,
missing permission evidence, malformed/non-finite pitch labels, duplicate record
IDs, local paths/audio payload fields, and voicebanks assigned to multiple
splits. A successful validation is **not** proof that a label is musically
correct or that the dataset license was independently verified; the recorded
approval must still be supported by human-reviewed evidence.

No real dataset is included. The tests use synthetic metadata fixtures only.
This is a data-ingestion safety gate, not a trained model or a claim of improved
pitch quality.
