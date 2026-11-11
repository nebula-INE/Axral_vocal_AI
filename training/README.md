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

The command validates the manifest and uses only records assigned to `train` for fitting. By default it reports mean absolute error (MAE) in semitones for train and validation, plus a zero-delta baseline (predict no pitch correction) and improvement over that baseline; negative improvement means the fitted model performed worse. The held-out test metrics are omitted unless `--evaluate-test` is explicitly supplied after model/settings decisions are finalized. This reduces the risk of tuning against the test set. Labels that fall outside any voiced note are counted and skipped. If any split has no usable voiced labels, the run fails instead of reporting misleading metrics. The JSON output includes the feature version, weights, split counts, model/baseline metrics, and explicit safety limitations. Prediction inputs are checked for non-finite values.

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

## Kaggle one-cell manifest discovery

The repository notebook at `kaggle/Axral_Vocal_AI_OneCell.ipynb` uses only the `HF_DATA_URL` setting. Its helper resolves the URL's Hub revision to a commit SHA, lists repository files, and downloads only supported voicebank archives, loose `oto.ini`/`prefix.map`/WAV files, and JSONL manifests. The default pre-download limit is 4096 MiB and the aggregate extracted-archive limit is 8192 MiB. The download summary also records the dataset-card `license` declaration when Hub metadata provides one and indexes selected `README.md`/`.txt`/`.rst`, `LICENSE`/`LICENCE`, `COPYING`, `NOTICE`, `COPYRIGHT`, `TERMS`, and `EULA` documents by relative path, size, and SHA-256. These declarations and document hashes are review aids only, not proof that every included voicebank permits Kaggle processing, ML training, or redistribution. The notebook copies this compact index into the downloadable run artifact; raw license/readme files and audio remain in the Kaggle data directory. ZIP/UAR-compatible and supported tar archives are extracted into an isolated directory; traversal paths, symlinks, hardlinks, special files, duplicate file paths, and byte-limit overruns are rejected. The dataset directory is cleared before each run so stale files from an earlier dataset or revision cannot contaminate the audit. If the Axral checkout already exists, the notebook checks that it is a clean Git worktree, fetches the latest `main`, and records the resulting source commit; it refuses to overwrite local edits or a non-Git directory. The notebook then audits discovered voicebank roots, runs pytest, and searches for JSONL manifests case-insensitively (for example, `.jsonl` and `.JSONL`). It adds the checkout to the notebook kernel's import path explicitly. Any archive extraction error, nonzero per-bank audit result, or pytest failure blocks the training step while preserving audit artifacts for diagnosis. The recommended filename is `pitch_training_manifest.jsonl` (it may be nested under a dataset subdirectory).

A manifest is eligible only when every row passes `training/validate_dataset.py --require-labeled`: schema version 1, explicit `permission_status: "approved"`, an approved provenance review, non-empty pitch-delta labels, finite values within ±2 semitones, and train/validation/test splits isolated by voicebank. Exactly one eligible manifest is required; zero or multiple candidates block training rather than choosing data implicitly. JSONL is expected to be UTF-8 and a UTF-8 BOM is accepted.

The current command trains only the **metadata-only pitch-delta ridge MVP** using note context and pre-existing pitch-delta labels. It does not open UTAU WAV files, learn from waveform samples, synthesize singing, or use the Kaggle GPU. A voicebank archive containing only `oto.ini` and WAV samples does not provide aligned score-to-pitch-delta ground truth; such a dataset will be audited and tested, but model training will be reported as blocked. Do not manufacture labels to bypass this gate.


## Archive diagnostics

Each archive receives its own summary entry with its repository-relative path, compressed byte size, extraction status, extracted byte count, and stable error code. Archive-level failures produce `completed_with_archive_errors` when other usable voicebanks were found, and they block training; the per-archive records remain in `download_summary.json`.


## Compact voicebank audit index

In addition to the full per-bank JSON reports, the Kaggle notebook writes `voicebank_audit_summary.json`. It aggregates numeric inventory/WAV/error/warning counters by bank index, records the failed audit exit codes, and deliberately omits bank paths, aliases, and raw filenames from this compact index. The full per-bank JSON files remain available under `audits/` for detailed local inspection.

## Japanese text and legacy ZIP filenames

The voicebank audit reader prefers UTF-8 for BOM-less metadata, accepts UTF-8 BOM and BOM-marked UTF-16, and falls back to CP932 when UTF-8 decoding fails. This preserves Japanese aliases in common UTAU `oto.ini` and `prefix.map` files without rewriting the source files. The Kaggle archive extractor also repairs a ZIP member name only when the ZIP UTF-8 flag is absent and the CP932 interpretation produces Japanese-script characters; UTF-8 names and non-Japanese CP437 names are left unchanged. Path-safety and duplicate-path checks run after this decoding step, so the repaired path—not the mojibake display string—is what gets validated and extracted. Ambiguous or already-corrupted source text cannot be reliably reconstructed automatically and remains subject to the audit report and manual review.
