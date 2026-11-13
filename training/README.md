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

The command validates the manifest and uses only records assigned to `train` for fitting. Validation is incremental rather than loading the whole JSONL into memory. Default safety bounds are 256 MiB per manifest, 1 MiB per JSONL line, and 100,000 records. The metadata MVP additionally stops above 1,000,000 label points or 250,000 usable training examples before constructing dense NumPy matrices. These caps are intentionally conservative for a Kaggle-first experiment; profile peak memory and raise them deliberately only after testing the target runtime. By default it reports mean absolute error (MAE) in semitones for train and validation, plus a zero-delta baseline (predict no pitch correction) and improvement over that baseline; negative improvement means the fitted model performed worse. The held-out test metrics are omitted unless `--evaluate-test` is explicitly supplied after model/settings decisions are finalized. This reduces the risk of tuning against the test set. Labels that fall outside any voiced note are counted and skipped. If any split has no usable voiced labels, the run fails instead of reporting misleading metrics. The JSON output includes the feature version, weights, split counts, model/baseline metrics, and explicit safety limitations. Prediction inputs are checked for non-finite values.

## Permission scopes (required for labelled training)

Every row in a labelled training manifest must carry an explicit `permissions` object. The accepted values for each scope are `approved`, `review_required`, or `prohibited`:

```json
{
  "permissions": {
    "local_processing": "approved",
    "hosted_processing": "review_required",
    "feature_extraction": "approved",
    "ml_training": "approved",
    "model_distribution": "review_required",
    "audio_redistribution": "prohibited"
  }
}
```

The execution context is explicit and defaults to local:

```bash
# Local training: requires local_processing, feature_extraction, and ml_training.
python training/train_pitch_model.py path/to/manifest.jsonl --execution-context local

# Kaggle or another hosted runner: requires hosted_processing, feature_extraction,
# and ml_training to be approved for every record.
python training/train_pitch_model.py path/to/manifest.jsonl --execution-context hosted
```

The one-cell Kaggle notebook always uses `execution_context="hosted"` and stops before deleting or downloading data unless the Kaggle Secret `AXRAL_HOSTED_PROCESSING_REVIEWED` is set to `yes`. Set that secret only after reviewing the exact terms for every selected voicebank and confirming that hosted processing on Kaggle is permitted. The editable notebook setting remains only `HF_DATA_URL`; the permission acknowledgment is stored separately as a secret. Approval for local processing does not authorize Kaggle/cloud processing. `model_distribution` and `audio_redistribution` are deliberately independent: successful training does not approve sharing a model, redistributing audio, or publishing a voicebank. A `review_required` or `prohibited` status in either distribution scope is allowed during training but must continue to block that separate activity.

These fields are an auditable human-entered permission record, not automatic legal verification. The reviewer must confirm the exact voicebank release, primary-source terms, allowed use, and evidence reference before setting an approval. Do not convert an unknown or ambiguous term into `approved`.

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

The repository notebook at `kaggle/Axral_Vocal_AI_OneCell.ipynb` uses only the `HF_DATA_URL` setting. Its helper resolves the URL's Hub revision to a commit SHA, lists repository files, and downloads only supported voicebank archives, loose `oto.ini`/`prefix.map`/WAV files, and JSONL manifests. Hugging Face glob metacharacters in repository filenames are escaped so the allowlist matches literal paths rather than accidentally selecting similarly named files. The pre-download limit is capped at 4096 MiB and the aggregate extracted-archive limit is capped at 8192 MiB; callers cannot raise these hard ceilings through function arguments. The download summary also records the dataset-card `license` declaration when Hub metadata provides one and indexes selected README and license documents (including localized variants such as `README_ja.md`, `README-ja.txt`, and `LICENSE_JP.md`) by relative path, size, and SHA-256. These declarations and document hashes are review aids only, not proof that every included voicebank permits Kaggle processing, ML training, or redistribution. The internal dataset summary indexes those documents during the run, but the downloadable artifact uses a path-free projection: it includes the declared license value and document count, not document paths or hashes. Raw license/readme files, archive paths, and audio are kept out of the artifact. ZIP/UAR-compatible and supported tar archives are extracted into an isolated directory; traversal paths, symlinks, hardlinks, special files, duplicate file paths, and byte-limit overruns are rejected. The pipeline permits at most 512 selected archives, 100,000 members per archive, and 250,000 members across all archives. TAR metadata is streamed without retaining `TarInfo` objects; ZIP central-directory entry counts are checked from the EOCD before `ZipFile` constructs its in-memory member index. The dataset directory is cleared before each run so stale files from an earlier dataset or revision cannot contaminate the audit. Raw archives and audio are stored temporarily under `/kaggle/temp/hf_voicebanks`, then removed during notebook finalization so they are not left in `/kaggle/working` outputs or included in `axral_run_artifacts.zip`. If the Axral checkout already exists, the notebook checks that it is a clean Git worktree, fetches the latest `main`, and records the resulting source commit; it refuses to overwrite local edits or a non-Git directory. The notebook then audits discovered voicebank roots, runs pytest,The notebook groups nested pitch-layer `oto.ini` folders under their outermost enclosing directory containing a regular, non-symlink `prefix.map`; independent roots without a shared `prefix.map` remain separate. It then audits the discovered voicebank roots and runs pytest, and searches for JSONL manifests case-insensitively (for example, `.jsonl` and `.JSONL`). It adds the checkout to the notebook kernel's import path explicitly. Any archive extraction error, nonzero per-bank audit result, missing/invalid per-bank report, invalid required `errors`/`warnings` counter, a positive report error count, or pytest failure blocks the training step. The notebook keeps detailed per-bank JSON reports only in `/kaggle/temp` during execution, then deletes them. Downloader, per-bank audit CLI, and JSONL-validator stdout is suppressed because it can contain archive paths or voicebank/record identifiers; only command exit codes are retained. Dataset-card identifiers, revisions, license identifiers, archive states, and error codes are format-checked and length-bounded before entering the public summary. Model metric keys, feature names, safety flags, and finite numeric weights are projected through a fixed allowlist. The downloadable artifact preserves only the compact audit index and sanitized pipeline log without paths, aliases, sample filenames, or record IDs. The index also aggregates validated `severity:issue_code` counts per bank and across the dataset (for example, `warning:metadata_replacement_character`) while omitting issue messages and source paths. Each per-bank row also receives a 16-hex `bank_fingerprint` derived from the dataset-relative root path. It provides a stable comparison key across reruns of the same repository layout without placing the original root path or bank directory name in the report. The recommended filename is `pitch_training_manifest.jsonl` (it may be nested under a dataset subdirectory).

A manifest is eligible only when every row passes `training/validate_dataset.py --require-labeled`: schema version 1, explicit `permission_status: "approved"`, an approved provenance review, non-empty pitch-delta labels, finite values within ±2 semitones, and train/validation/test splits isolated by voicebank. Exactly one eligible manifest is required; zero or multiple candidates block training rather than choosing data implicitly. JSONL is expected to be UTF-8 and a UTF-8 BOM is accepted.

The current command trains only the **metadata-only pitch-delta ridge MVP** using note context and pre-existing pitch-delta labels. It does not open UTAU WAV files, learn from waveform samples, synthesize singing, or use the Kaggle GPU. A voicebank archive containing only `oto.ini` and WAV samples does not provide aligned score-to-pitch-delta ground truth; such a dataset will be audited and tested, but model training will be reported as blocked. Do not manufacture labels to bypass this gate.


## Archive diagnostics

During execution, each archive receives an internal summary entry with its repository-relative path, compressed byte size, extraction status, extracted byte count, and stable error code. Archive-level failures produce `completed_with_archive_errors` when other usable voicebanks were found, and they block training. The full per-archive records stay in the temporary dataset directory and are deleted after the cell finishes; the downloadable `download_summary.json` contains only aggregate counts and error-code counts.


## Compact voicebank audit index

The Kaggle notebook writes `voicebank_audit_summary.json`, aggregating numeric inventory/WAV/error/warning counters by bank index and recording stable failure codes without bank paths, aliases, or raw filenames. Full per-bank JSON reports are created under `/kaggle/temp/hf_voicebanks/audit_reports` only while the cell is running; they are deleted during finalization and are not included in the downloadable artifact. The ZIP contains only an allowlist: sanitized `pipeline.log`, path-free `download_summary.json`, `voicebank_audit_summary.json`, `summary.json`, and an ID-free metadata-only model metrics projection when one exists. The trainer's original report (which contains voicebank IDs by split) stays under `/kaggle/temp` and is deleted before packaging; only aggregate split counts, MAE/baseline metrics, and model weights are retained.

## Japanese text and legacy ZIP filenames

The voicebank audit reader prefers UTF-8 for BOM-less metadata, accepts UTF-8 BOM and BOM-marked UTF-16, and falls back to CP932 when UTF-8 decoding fails. This preserves Japanese aliases in common UTAU `oto.ini` and `prefix.map` files without rewriting the source files. If either metadata file already contains U+FFFD replacement characters, the audit emits `metadata_replacement_character` with a line number; it preserves the parsed text but flags that the original characters cannot be reconstructed automatically. The Kaggle training gate treats this warning as critical and refuses training for that dataset run, even when the per-bank audit CLI exits successfully. The audit also emits `metadata_suspected_mojibake` only when a line containing a known mojibake marker can be encoded as CP932 and decoded as different UTF-8 Japanese text. This strict reversible-byte check avoids flagging ordinary Japanese text merely because it contains one or more marker characters. The recovered text is used only to confirm the signature and is never written back; the Kaggle training gate blocks the run on this warning so potentially corrupted aliases or prefix suffixes are not silently used as labels or metadata. The Kaggle archive extractor also repairs a ZIP member name only when the ZIP UTF-8 flag is absent and the CP932 interpretation produces Japanese-script characters; UTF-8 names and non-Japanese CP437 names are left unchanged. Path-safety and duplicate-path checks run after this decoding step, so the repaired path—not the mojibake display string—is what gets validated and extracted. Ambiguous or already-corrupted source text cannot be reliably reconstructed automatically and remains subject to the audit report and manual review.


## Kaggle manifest diagnostics

The one-cell Kaggle run records path-free `training_diagnostic_code` and
`manifest_validation_failure_codes` in `summary.json` and `pipeline.log`.
Each rejected JSONL candidate is represented only by its numeric candidate
index and a stable error code; exception messages, record IDs, voicebank
names, lyrics, filenames, and local paths are not copied into the artifact.
Codes distinguish missing manifests, invalid UTF-8/JSON, size and record
limits, permission/provenance failures, split leakage, malformed note data,
and missing or invalid pitch labels. These diagnostics explain why the
metadata-only pitch-delta MVP did not train; they do not imply that WAV
inventory alone is sufficient training data.
