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
