# Pitch-delta experiment readiness checklist

This checklist is a gate before running any real-data experiment, including on Kaggle.
The current model is an experimental metadata-only ridge-regression baseline. Passing
these checks does not establish musical quality, naturalness, or production readiness.

## 1. Data rights and privacy — stop if any item is uncertain

- [ ] Confirm written permission covers machine-learning training and evaluation, not only ordinary voicebank use.
- [ ] Record the applicable license/permission reference and the person/date who reviewed it.
- [ ] Do not upload voice samples, raw audio, private paths, credentials, or identifying metadata to a notebook.
- [ ] Keep the dataset and notebook private; do not publish datasets, checkpoints, or outputs without a separate review.
- [ ] Treat `permission_status: approved` as a manifest assertion, not legal verification.

## 2. Manifest validation

Run the metadata validator first, then the training script only after validation succeeds.
Use the repository's documented commands in `training/README.md`; do not bypass validation.

- [ ] Every record has a unique `record_id`, an approved source, a non-empty license reference, and valid note/label values.
- [ ] All pitch-delta labels are finite and within +/-2 semitones.
- [ ] Each voicebank belongs to exactly one of train, validation, or test.
- [ ] Each source belongs to exactly one split.
- [ ] Train, validation, and test each contain usable voiced labels.
- [ ] Review the generated split summary and label counts before interpreting metrics.

## 3. Small CPU-first experiment

- [ ] Start with a small, rights-cleared metadata-only manifest and CPU execution.
- [ ] Record the repository commit, Python/dependency versions, manifest version, split counts, and ridge alpha.
- [ ] Compare train/validation/test MAE with the zero-delta baseline; do not judge by training MAE alone.
- [ ] If validation performance is worse than the zero-delta baseline, do not promote the model.
- [ ] Inspect errors by voicebank and note range where the dataset supports that analysis.
- [ ] Repeat with a fresh run before drawing conclusions; tiny synthetic fixtures test plumbing only.

## 4. Promotion is a separate decision

- [ ] Report test metrics only after model/settings decisions are complete using validation data.
- [ ] Document known dataset limitations and any distribution imbalance.
- [ ] Require a separate review of model behavior and integration safety before any production use.
- [ ] Do not connect this experimental model to the production renderer or change audio synthesis as part of this experiment.

## Current status

No real dataset has been trained or evaluated by this repository's synthetic CI tests.
Do not treat CI success as evidence of pitch quality or as approval to use any particular
voicebank. If data rights or split isolation cannot be established, stop before uploading
or training.

## Status and realistic path to the first meaningful training run — 2026-10-11

### What is already implemented

- A metadata-only JSONL manifest validator with source approval assertions, provenance fields, finite/range checks, and voicebank/source split-leakage checks.
- A deterministic zero-delta baseline, a small ridge-regression training loop, and train/validation metrics compared against that baseline.
- A synthetic CI fixture that exercises training plumbing only. Its success is not evidence that the model has learned useful singing expression.
- Request/response contracts and a runtime characterization of selected Desktop/Web pitch helper behavior. The AI proposal is not connected to the production renderer.

### Remaining hard blockers

1. **Real-data permission:** identify at least one concrete source and retain evidence that its terms permit ML training, derived labels, the selected storage/notebook service, evaluation, and the intended model/output distribution. An `approved` manifest value is only an assertion; it is not a substitute for reviewing the evidence.
2. **Usable labels:** define how a pitch target is produced and reviewed (for example, curated pitch-expression contours with a documented reference and confidence). Do not treat arbitrary existing automation as ground truth until its units and meaning are calibrated.
3. **Voicebank-isolated splits:** freeze a reproducible train/validation/test manifest with no source or voicebank crossing split boundaries and enough usable voiced labels in every split.
4. **Feature/model adequacy:** the current five-feature linear ridge model is a training-pipeline smoke-test baseline, not a validated expressive singing model. Evaluate it against zero-delta first; if it does not beat the baseline on held-out voicebanks, do not promote it. Only then expand context features and compare a more capable model.
5. **Reproducible experiment record:** record commit, dependency versions, data/manifest version, split counts, seed/configuration, runtime/resources, and metrics before interpreting results.

### Estimate (planning range, not a promise)

- **First real-data training run:** approximately 2–5 focused working days *after* rights-cleared data and reviewed labels are actually available, assuming the initial dataset is small and metadata-only. The current code can already run the synthetic smoke test; that is not the real-data milestone.
- **First defensible held-out evaluation:** roughly 1–3 additional weeks after a suitable multi-voicebank labeled dataset is assembled, depending on annotation volume and label consistency.
- **Useful, integration-ready pitch assistance:** no reliable calendar estimate yet. It requires iterative listening/evaluation, unseen-voicebank tests, and safe preview-only integration; a successful training command alone is not sufficient.

The largest unknown is not GPU setup or Kaggle execution time. It is obtaining legally usable, consistently labeled examples that teach the behavior we want. Do not upload voicebanks or project/audio material to Kaggle until the source review explicitly permits that service.

