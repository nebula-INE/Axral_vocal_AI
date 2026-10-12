# Pitch-expression labels and evaluation — Draft 2

This document defines the minimum evaluation contract before real data or GPU training. It does not authorize use of any voicebank, recording, project, or pitch curve.

## 1. Target definition

The initial model target is a pitch-expression offset in **semitones**, relative to an explicitly documented reference pitch trajectory:

`delta_semitones(t) = target_pitch_semitones(t) - reference_pitch_semitones(t)`

The reference and target must be produced by a documented method. Do not assume an existing `PitchEvent.value` is in semitones.

### Existing VO-SE_vocal representations found in the audit

These are distinct data domains and must not be conflated:

- **Sparse project/GUI automation points:** `PitchEvent(time, value)`; `time` is seconds, but `value` is only a float in the data model. The graph editor constrains Pitch values to -8192..8191.
- **Automation sampling:** Python `GraphEditorWidget.get_value_at_time()` and native `AutomationCurves::evaluate()` both use step-hold (last point at or before the query time). The GUI draws straight lines between points, so visual interpolation differs from the sampled value behavior.
- **Native automation conversion:** `AutomationRanges::pitchValueToSemitones()` currently calculates `(value / 8191) * 2.0`, and the native processor applies that as a frequency ratio. This defines a current native conversion, but does not prove all project, imported, or Web values share that meaning. Its endpoints are asymmetric (-8192 becomes slightly below -2 semitones; +8191 becomes +2).
- **Render input pitch curve:** native interfaces expose dense per-sample `pitch_curve` arrays in Hz. These are not sparse automation values and are not semitone deltas.
- **Timeline overlay:** the UI uses a similar ±2-semitone display conversion; display behavior alone does not verify every render path.

Therefore, the conversion from existing `PitchEvent.value` to AI semitone labels remains **blocked** until the intended data path (including Web serialization and render handoff) is traced and covered by tests. Do not change production formulas just to make them symmetric during this AI work.

A label record must identify:
- target kind: `pitch_delta_semitones`;
- label source: curated reference, expert annotation, or synthetic fixture;
- source method/tool and version;
- timestamp unit and time-grid policy;
- voiced/unvoiced treatment;
- annotator/reviewer and review status when applicable;
- confidence and its defined meaning, if supplied.

Synthetic fixture labels are only for testing plumbing. They must never be mixed into real-world quality claims without separate reporting.


## 2A. Deterministic pitch-track label construction

The metadata-only helper axral_vocal_ai.pitch_labels.build_pitch_delta_labels creates labels from two already-reviewed pitch tracks. It does not estimate pitch from audio and is not a substitute for human review.

- Both tracks must already use semitones and the same absolute time_sec grid. Mismatched grids are rejected; the helper never aligns, interpolates, smooths, or resamples.
- Every point must explicitly identify voiced/unvoiced state. Unvoiced pairs are omitted; no label is synthesized across a gap.
- A configured min_confidence requires confidence on every voiced point. Pairs below the threshold are omitted. The confidence value and threshold must be documented by the caller; the helper does not prescribe an estimator-specific threshold.
- The delta is always target_pitch_semitones - reference_pitch_semitones. Non-finite values, duplicate/out-of-order timestamps, invalid confidence, and deltas outside +/-2 semitones are rejected. Values are never silently clipped.
- The output contains only time_sec and delta_semitones. The caller must still attach reviewed source/license/provenance metadata and pass the result through the manifest validator before training.

This helper establishes deterministic arithmetic and input validation only. It does not verify source rights, prove that a pitch track is ground truth, or demonstrate singing quality.

## 2. Label inclusion rules

- Include only samples whose machine-learning use, storage, derived labels, and model distribution permissions have been reviewed and approved.
- Exclude `review_required` and `prohibited` sources from training, validation, test, and Kaggle uploads.
- Do not label unvoiced/rest regions as voiced pitch targets. If a model later predicts voiced/unvoiced state, define and evaluate that as a separate task.
- Do not infer ground truth from an arbitrary existing pitch curve without checking how it was authored, processed, and scaled.
- Keep unresolved aliases explicitly unresolved; do not silently substitute another sample or phoneme.
- Preserve source timestamps. Any interpolation/resampling must be a named, versioned preprocessing operation and tested separately.

## 3. Evaluation metrics

Report all metrics on a fixed, documented time grid and only over eligible voiced target points unless a metric explicitly says otherwise.

1. **MAE (semitones)** — primary metric; average absolute difference between predicted and reference deltas.
2. **RMSE (semitones)** — secondary metric; highlights larger errors.
3. **Mean signed error (semitones)** — detects systematic sharp/flat bias.
4. **Coverage** — fraction of eligible reference points for which a prediction was produced; report separately so a model cannot appear better by skipping hard points.
5. **Per-voicebank metrics** — report each held-out voicebank and macro-average across voicebanks; do not rely only on a pooled frame average.

Baseline and model must use the same records, time grid, voiced mask, and aggregation policy. Report the deterministic zero-delta baseline alongside any learned model. No single aggregate metric is sufficient to establish naturalness or audio quality.

## 4. Split and leakage policy

- Split by complete `voicebank_id`, not by random frames or adjacent snippets from the same bank.
- Freeze a deterministic split manifest with dataset version and seed before tuning.
- Keep the final test voicebanks untouched during model selection.
- When too few independent voicebanks are approved, document that limitation and do not claim cross-voicebank generalization.
- Store only opaque IDs and provenance metadata in this repository; keep permitted audio and private paths in access-controlled storage.

## 5. Gate before Kaggle

Kaggle training remains blocked until:
- [ ] the exact source license/permission covers intended ML use, storage, derived labels, and model distribution;
- [ ] label creation and pitch-unit conversion have documented, tested procedures;
- [ ] Desktop/Web serialization and render handoff for the selected input representation are traced and tested;
- [ ] data manifests contain no private paths, credentials, or unapproved audio;
- [ ] voicebank-held-out split is reviewed and reproducible;
- [ ] baseline metrics run successfully on the frozen fixture and, when approved data exists, on the same evaluation protocol as the candidate model.

Passing these gates permits a small experiment only. It does not permit integration with VO-SE_vocal's production renderer.
