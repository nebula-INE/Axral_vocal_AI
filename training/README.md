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

Then train the small ridge-regression MVP and evaluate train/validation metrics:

```bash
python training/train_pitch_model.py path/to/manifest.jsonl --output artifacts/pitch_delta_report.json
```

By default, the command reports train and validation metrics only. After model and settings decisions are finalized using validation data, evaluate the held-out test split once by explicitly adding:

```bash
python training/train_pitch_model.py path/to/manifest.jsonl --output artifacts/pitch_delta_report.json --evaluate-test
```

The command validates the manifest and uses only records assigned to `train` for fitting. By default it reports mean absolute error (MAE) in semitones for train and validation, plus a zero-delta baseline (predict no pitch correction) and improvement over that baseline; negative improvement means the fitted model performed worse. The held-out test metrics are omitted unless `--evaluate-test` is explicitly supplied after model/settings decisions are finalized. This reduces the risk of tuning against the test set. Labels that fall outside any voiced note are counted and skipped. If any split has no usable voiced labels, the run fails instead of reporting misleading metrics. The JSON output includes the feature version, weights, split counts, model/baseline metrics, and explicit safety limitations. Prediction inputs are checked for non-finite values. The report also includes a `validation_assessment` and `quality_warnings`: if validation MAE ties or loses to the zero-delta baseline, training may complete for diagnostic purposes, but the report explicitly says no benefit has been demonstrated and the model should not be used without investigation. It also reports label coverage and skipped-label rates overall, by split, and by voicebank. `label_use_rate` only means that a label timestamp mapped to a usable note; it does **not** measure acoustic correctness or prove that the target label is musically valid. Always inspect counts alongside rates, especially for small groups.

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
