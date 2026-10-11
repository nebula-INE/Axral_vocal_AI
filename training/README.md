# Training workspace (Kaggle-first proposal)

Kaggle is an optional hosted experiment environment, not a permanent production dependency. Use it for reproducible small experiments only after data rights, target labels, and evaluation splits are defined. Do not start expensive GPU sessions before a baseline and evaluation split exist.

## Notebook workflow

1. Keep notebooks in a separate private Kaggle notebook or private dataset while data rights and contents are being reviewed.
2. Record dataset source, license/permission, allowed uses, attribution requirements, and restrictions before importing data.
3. Start with a CPU-only data audit and synthetic fixtures. The repository includes a data-free zero-delta baseline and a metadata-only training smoke test.
4. Split train/validation/test by voicebank. Do not tune against the held-out test split.
5. Record environment/package versions, data version, configuration, duration, peak memory, and metrics.
6. Only then compare accelerator settings or expand the corpus.
7. Export a model report with model version, feature version, training data identifiers, preprocessing version, metrics, and limitations.
8. Never commit private datasets, voicebank WAVs, credentials, notebook secrets, or large checkpoints.

## Implemented: permission gate and experimental training loop

Install the training dependencies:

```bash
python -m pip install -e ".[dev,training]"
```

Validate the metadata-only JSONL manifest first:

```bash
python training/validate_dataset.py path/to/manifest.jsonl --require-labeled
```

Then train the small ridge-regression MVP and evaluate it on the preassigned validation and test voicebanks:

```bash
python training/train_pitch_model.py path/to/manifest.jsonl --output artifacts/pitch_delta_report.json
```

The command validates the manifest, uses only records assigned to `train` for fitting, and reports mean absolute error in semitones for train, validation, and test. Labels that fall outside any voiced note are counted and skipped. If any split has no usable voiced labels, the run fails instead of reporting misleading metrics. The JSON output includes the feature version, weights, split counts, metrics, and explicit safety limitations.

## Scope and limitations

- This is a tiny linear ridge-regression model over note pitch, relative note phase, and note duration; it is **not** a neural singing synthesis model.
- Training and inference operate on metadata only; no audio files are read.
- A successful run on synthetic data proves only that the training/evaluation plumbing works. It is not evidence of musical quality, naturalness, or generalization.
- The model is proposal-only and is not connected to VO-SE_vocal, its renderer, or any project-editing path.
- No real dataset or trained weights are included. A real run requires independently reviewed permission, trustworthy labels, and held-out voicebanks.
- Manifest status `approved` is not independent legal verification. Humans must verify the underlying evidence and allowed ML use.
- Do not integrate the output into production until separate evaluation, bounded-output policy, listening tests, and renderer regression checks are reviewed.

## Reproducibility record

For each run, preserve dataset identifiers and permission status (without private content), voicebank-level splits, label definition, feature version, alpha, package versions, metrics, artifact checksum, and known limitations. Do not upload copyrighted or restricted data to Kaggle unless the license and consent explicitly permit hosted processing.
