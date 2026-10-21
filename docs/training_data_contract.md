# Training data contract (draft)

Status: specification only. No training dataset, trained model, or inference-quality claim is implied by this document.

## Goals and boundaries

The first model target is an editable pitch-expression proposal. Training examples must describe a desired pitch delta relative to an existing note baseline; they must not be rendered WAV replacements, alias substitutions, or changes to note timing.

This contract applies to data preparation and evaluation in `Axral_vocal_AI`. It does not authorize changes to VO-SE_vocal's renderer, synthesis, export, WAV writing, timing, pitch shifting, or audio processing.

## Implementation status and schema boundaries

Two validators currently coexist, and they intentionally serve different record shapes:

- `src/axral_vocal_ai/training_data.py` validates the existing manifest format (`schema_version: 1`, `record_id`, `permission_status`, `input.notes`, absolute-second timing, and `delta_semitones`). It also checks voicebank/source split leakage.
- `src/axral_vocal_ai/pitch_training_contract.py` validates the example-level contract documented below (`record_schema: axral.pitch-training-example`, string version `1.0`, `example_id`, explicit consent/provenance, note-relative milliseconds, baseline pitch in Hz, and target deltas in cents). It returns per-record rejection codes and aggregate counts.

These formats are **not interchangeable**. Do not feed one format to the other validator, silently rename fields, or convert units without an explicit, tested migration. The example-level validator validates individual JSONL records and reports duplicate IDs within a JSONL input. `src/axral_vocal_ai/pitch_training_contract_splits.py` assigns deterministic splits directly to that example-level shape and keeps connected voicebank/source/project/session groups together. Separately, `src/axral_vocal_ai/pitch_training_splits.py` generates deterministic splits for the **legacy manifest format only** and reuses `validate_records` as a final leakage gate. The existing legacy manifest validator still validates already-assigned splits; it does not generate assignments itself.

The metadata-only preparation orchestrator is available through `src/axral_vocal_ai/pitch_training_pipeline.py`: `prepare_legacy_dataset(...)` and `prepare_example_dataset(...)` each call only their matching schema's deterministic split generator, then run the corresponding quality report. They return prepared metadata records, the aggregate report, and `status: ready_for_manual_review`; this status is not training authorization or evidence of real-data rights/quality. Invalid input is rejected before preparation, input records are not mutated, and `training_started` remains false. The pipeline does not load audio, repair labels, or start model training. `src/axral_vocal_ai/pitch_training_readiness.py` adds a separate, stricter metadata gate (`assess_training_candidate(...)`) for both schemas; a positive result only advances a candidate to human training review and never starts training.

The metadata-only quality report is available through `src/axral_vocal_ai/pitch_training_quality.py`: call `report_legacy_records(...)` for legacy rows or `report_example_records(...)` for example-level rows. Reports include validation issue counts, split/source/consent/review/label distributions, and voicebank-group counts while omitting raw IDs and sample content. For both schemas, records that share a split-group identity across different assigned splits are counted as leakage and all affected records are marked invalid; the example-level report checks voicebank split group, source ID, and optional project/session/source-group IDs. `dataset_origin` defaults to `synthetic_fixture`; `candidate_real_data` only changes the report warning and does not certify permissions, provenance, or label quality. The documented example format is the intended shape for new note-level pitch training examples. Its direct split generator groups records by `voicebank.split_group`, `provenance.source_id`, and optional `provenance.project_id`, `provenance.session_id`, or `provenance.source_group_id`. The legacy split generator continues to use its own manifest fields and policy. These split generators do not convert between schemas or establish that a usable training dataset exists; keep the validators separate and treat passing validation as necessary but not sufficient.
## Example record

The following is a JSON Lines record shape for a *metadata/label record*. Values are illustrative and are not training data.

```json
{
  "record_schema": "axral.pitch-training-example",
  "schema_version": "1.0",
  "example_id": "example-000001",
  "provenance": {
    "source_kind": "human_labeled_project",
    "source_id": "opaque-source-id",
    "license_or_permission": "documented-permission-reference",
    "consent_status": "verified",
    "created_at": "2026-01-01"
  },
  "voicebank": {
    "profile_id": "opaque-bank-id",
    "profile_version": "1",
    "phoneme_scheme": "utau-alias",
    "split_group": "opaque-bank-id"
  },
  "context": {
    "midi_note": 60,
    "start_ms": 0.0,
    "duration_ms": 500.0,
    "lyric": "あ",
    "resolved_alias": "あ",
    "voiced": true,
    "baseline_pitch": [
      { "time_ms": 0.0, "hz": 261.6256 },
      { "time_ms": 250.0, "hz": 261.6256 },
      { "time_ms": 500.0, "hz": 261.6256 }
    ]
  },
  "target": {
    "kind": "pitch_delta",
    "points": [
      { "time_ms": 0.0, "delta_cents": 0.0 },
      { "time_ms": 250.0, "delta_cents": 18.0 },
      { "time_ms": 500.0, "delta_cents": 0.0 }
    ],
    "label_source": "human_reviewed",
    "review_status": "approved"
  }
}
```

## Validation requirements

A preparation pipeline should reject or quarantine records when any of these conditions holds:

- Schema name/version is missing or unsupported.
- Provenance, permission reference, consent status, or stable example ID is missing.
- The same `example_id` occurs more than once.
- MIDI note is not an integer in 0..127; times or pitch values are non-finite; duration is negative.
- Baseline/target point times are not ordered, are outside the note duration, or target values contain invalid/non-finite deltas.
- A target pitch delta overlaps a region explicitly marked unvoiced/rest.
- Alias/sample resolution is missing, ambiguous, or inconsistent with the recorded voicebank profile.
- A label was generated by the deterministic no-op stub. Stub output is for contract plumbing only and is never a ground-truth label.
- Permission is unknown, withdrawn, or not sufficient for the intended training/evaluation use.

Do not silently clamp, repair, or invent labels. Keep a machine-readable rejection reason and aggregate counts; do not expose local absolute paths in reports by default.

## Split and leakage policy

- Split by `voicebank.split_group` before expanding clips, notes, or augmentations. A voicebank used for training must not also appear in the held-out voicebank test split.
- Keep all derived records from one original project/session in the same split to prevent near-duplicate leakage.
- Keep a validation split separate from the final test split. Freeze test-set membership before tuning.
- Report results separately for unseen voicebanks and for any within-bank diagnostic set; do not combine them into a single headline score.
- Record split seed, source manifest hash, preprocessing version, and code revision for every run.

## Data minimization and storage

- Do not commit voicebank WAV files, raw projects, credentials, or personal data to this repository by default.
- Store only the minimum features and labels required for the task. Use opaque IDs rather than local filesystem paths or identifying project names.
- Keep data outside Git unless licensing, consent, retention, access control, and repository storage policy have been explicitly reviewed.
- Provide a documented removal path for withdrawn data and regenerate derived manifests/features when required.
- Do not infer permission from a file being publicly downloadable or from an open-source tool being used to read it.

## Required evaluation report

Each training/evaluation run should record:

- dataset manifest hash, code revision, model ID/version, split policy, and random seed;
- counts of accepted/rejected examples and rejection reasons;
- metrics on held-out voicebanks, including pitch-delta error in cents, invalid-output rate, and rest/unvoiced violation rate;
- temporal smoothness/continuity diagnostics and a baseline comparison;
- per-phoneme/alias-family and per-voicebank breakdowns where sample counts are sufficient;
- runtime and memory measurements for each intended inference backend;
- limitations, known coverage gaps, and any manual-review requirement.

A passing unit test or low numeric error alone does not establish musical quality or compatibility. Human listening and editable-proposal review are required before any product integration.

## Implementation gates

1. Implement a strict record parser/validator with unit tests. **Implemented** for the documented example-level schema; the separate existing manifest validator remains in place.
2. Implement deterministic split generation with leakage checks for the legacy manifest and example-level formats. **Implemented separately for both formats**; the metadata-only end-to-end data-preparation/reporting path is implemented in `pitch_training_pipeline.py`.
3. Add a report generator that works on synthetic fixtures only. **Implemented** in `src/axral_vocal_ai/pitch_training_quality.py`; `report_legacy_records` and `report_example_records` stay schema-specific, emit aggregate counts only, and label fixture/candidate origins explicitly. Candidate-real-data mode is not a rights or quality certification.
4. Add licensed, consented examples only after their provenance is verified. The readiness gate in `pitch_training_readiness.py` checks declared permission/consent, review status, labels, split coverage, and metadata leakage, but cannot independently verify the underlying claims.
5. Train a baseline and evaluate on voicebanks excluded from training.
6. Connect a trained model to the wire contract only after quality, runtime, data-rights, and fallback gates pass.

Until those gates are complete, the existing deterministic stub remains a contract test fixture, not an AI model.

## Evaluation manifest validator

`src/axral_vocal_ai/pitch_training_evaluation.py` provides
`validate_evaluation_manifest(...)` for recording a reproducible evaluation
summary. The manifest requires the dataset snapshot SHA-256, model artifact
SHA-256, code revision, random seed, schema, positive evaluated-record count,
named finite numeric metrics, and an explicit `evaluated_split: test`.
It rejects a manifest that says the test split was used for tuning.

A valid manifest returns `status: ready_for_human_review`; it does not run
evaluation or training and does not prove the supplied hashes match artifacts,
that the test set is independent, or that reported metrics are truthful.
Only metric names and reproducibility metadata are returned in the summary;
raw samples and record identifiers are not copied into it. This is an
auditability guard, not a substitute for a real held-out evaluation protocol.
