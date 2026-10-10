# Training Record Schema — Draft 1

This is a metadata-first proposal for the first pitch-expression model. It is not a commitment to upload or redistribute any voicebank audio.

## Design constraints

- Every record must have documented provenance and a permission/license decision before use.
- Raw audio and absolute local paths are stored only in a private, access-controlled dataset location when permitted. They must not be committed to this repository.
- Evaluation splits must hold out complete voicebanks where the dataset size permits.
- Preserve source alias and note context for auditing; never pretend an unresolved alias was resolved.
- The first model predicts pitch-expression deltas only. It does not synthesize waveform audio.

## Record fields

| Field | Type | Required | Meaning |
|---|---|---:|---|
| schema_version | integer | yes | Dataset record schema; initially 1 |
| record_id | string | yes | Stable opaque ID, not a filesystem path |
| source_id | string | yes | Opaque source/dataset identifier |
| permission_status | enum | yes | `approved`, `review_required`, or `prohibited` |
| license_id | string or null | yes | SPDX identifier or documented internal permission reference; null means unresolved |
| voicebank_id | string | yes | Stable opaque ID used for group-based splitting |
| split | enum | yes | `train`, `validation`, or `test`; assigned by voicebank, not random frames |
| input | object | yes | Note and optional voicebank context |
| target | object or null | yes | Human/curated pitch-expression delta labels; null for unlabeled examples |
| provenance | object | yes | Acquisition method, source reference, review date, reviewer/status |
| preprocessing | object | yes | Tool/version, sample rate if audio was processed, and transformation list |

## Input object

- `notes`: ordered list of `start_sec`, `end_sec`, `midi_note`, original `lyric`, optional `resolved_alias`, and optional `voiced`.
- `tempo_bpm` and `time_signature`: optional musical context.
- `voicebank_profile`: optional counts, alias-pattern hints, parser version, and pitch-bank boundaries. Never include absolute paths or audio bytes.

## Target object

- `kind`: initially `pitch_delta_semitones`.
- `points`: ordered list of `time_sec` and `delta_semitones`.
- `label_source`: e.g. `curated_reference`, `expert_annotation`, or `synthetic_fixture`.
- `confidence`: optional value in [0, 1], with documented meaning.

Labels must describe an explicit reference and method. Do not treat an arbitrary existing pitch curve as ground truth without checking how it was created. Do not label unvoiced regions as voiced pitch targets.

## Permission gate

Before a source can enter a training split, a human must verify that the actual license or permission covers the intended machine-learning use, storage location, derived labels, and any distribution of resulting models. Public availability alone is not permission. Anything marked `review_required` or `prohibited` must be excluded from training and Kaggle uploads.

## Split policy

1. Group all examples by `voicebank_id`.
2. Reserve at least one complete voicebank for final held-out testing when there are enough independent banks.
3. Do not tune model settings against the held-out test bank.
4. Keep a deterministic split manifest with the dataset version.
5. If too few independent voicebanks exist, report that limitation instead of claiming cross-voicebank generalization.

## Initial baseline

Start with synthetic fixtures and a deterministic no-learning baseline. Establish evaluation code and expected input/output shapes before downloading data or allocating a GPU. The baseline must be reproducible and must not touch the production renderer.
