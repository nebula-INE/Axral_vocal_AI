# Training-data source review gate

Status: **blocked until each source is reviewed**. This checklist is a recordkeeping template, not legal advice and not permission to use any particular dataset.

No audio, voicebank, project file, extracted feature, pitch label, or model checkpoint may enter a training run merely because it is publicly downloadable or usable in VO-SE_vocal.

## 1. One review record per source

Create a separate record for every dataset, voicebank, recording collection, or annotation source. Record at least:

- [ ] Stable source ID and exact source name/version.
- [ ] Original publisher/creator and canonical source location.
- [ ] Acquisition date and method; retain evidence of the terms shown at acquisition.
- [ ] Applicable license, terms of service, and any separate consent or permission.
- [ ] Whether permission explicitly covers: machine-learning training, storage/copying, preprocessing, derived pitch labels/features, validation and testing, use by external hosted services, and distribution of model weights or outputs.
- [ ] Attribution, share-alike, non-commercial, field-of-use, redistribution, deletion, and access restrictions.
- [ ] Personal-data, performer consent, publicity/personality rights, and other jurisdiction-specific issues that require review.
- [ ] Intended use and approved storage location; who reviewed it, when, and what evidence supports the decision.
- [ ] Decision: `approved`, `review_required`, or `prohibited`; include a rationale and review date.

Do not infer a permission from silence. If any material right or term is unclear, set the decision to `review_required` and exclude the source.

## 2. Decision meanings

- **approved** — documented evidence has been reviewed for the exact intended use, including training, derived labels, storage, evaluation, and the planned model/output distribution. Approval is scoped to the recorded version and use.
- **review_required** — evidence is missing, ambiguous, conflicting, or awaiting a qualified review. Exclude from all training and hosted notebook uploads.
- **prohibited** — known terms or permission do not allow the intended use, or the source has been rejected. Do not ingest or retain training copies beyond what is needed to handle the source in accordance with applicable obligations.

A source approved for listening, editing, or synthesis is not automatically approved for ML training. A permission to train is not automatically permission to redistribute weights or expose source-derived material.

## 3. Dataset manifest and handling

- Keep a versioned manifest with opaque source IDs, source versions, decision, review record reference, preprocessing version, and split assignment.
- Keep private paths, credentials, source audio, and private project material out of Git. Store permitted media only in access-controlled storage with a documented retention/deletion policy.
- Do not upload material to Kaggle or another third-party service until the source review explicitly covers that service and its storage/processing terms.
- Keep synthetic fixtures separate from real-source data and report their results separately.
- Freeze the source manifest and voicebank-held-out split before tuning. Any change to source rights, versions, labels, or preprocessing requires a new manifest version and review.
- Re-check permissions before publishing a dataset, checkpoint, model weights, demo, or other derived artifact.

## 4. Release gate

A training run may start only when every included source is `approved`, its use matches the approval scope, and the label procedure and split manifest are reproducible. If no source meets that bar, continue only with synthetic fixtures and the deterministic zero-delta baseline.

Passing this gate does not authorize changes to VO-SE_vocal's production renderer or audio pipeline.
