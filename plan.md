# Hugging Face UTAU Voicebank CI Audit Plan

## Goal

Add a dedicated GitHub Actions workflow that retrieves UTAU voicebank data from the Hugging Face dataset repository `SEKOIA2900/VO-US` and runs Axral Vocal AI's existing, read-only voicebank audit against the retrieved data.

The workflow is a data-compatibility and parser-regression gate. It is not an AI training workflow and must not upload voicebank audio or detailed voicebank contents to GitHub artifacts.

## Source of truth

- Hugging Face dataset: [SEKOIA2900/VO-US](https://huggingface.co/datasets/SEKOIA2900/VO-US/tree/main)
- Default revision: `main`; resolve it to an immutable commit SHA at the beginning of each run and record that SHA in the summary.
- Discover files from the Hub API rather than assuming a fixed archive or directory layout.
- Retrieve UTAU-relevant files: supported voicebank archives (`zip`, `uar`, supported tar formats), standalone `oto.ini`, `prefix.map`, and WAV/audio files needed to validate references.

## Execution policy

- Keep the existing `.github/workflows/tests.yml` as the fast, per-pull-request unit/integration CI.
- Add a separate manual-only workflow with a default-deny hosted-processing permission gate; keep automatic schedules disabled until per-bank permissions are reviewed.
- Provide inputs for dataset revision, optional voicebank path/name filter, maximum download size, and failure threshold.
- Set least-privilege GitHub permissions, a bounded job timeout, and artifact retention.
- Use a public read-only Hub request by default. An optional Hugging Face read token may be supplied as a GitHub secret; never print it.

## Processing pipeline

1. Resolve the selected Hugging Face dataset revision to a commit SHA.
2. List repository files and identify UTAU archives or standalone UTAU metadata/audio.
3. Estimate the selected download size before downloading; stop with a clear error when the configured limit would be exceeded.
4. Download only selected files, not unrelated dataset content.
5. Extract supported archives into isolated directories. Reject archive entries that are absolute, escape the extraction root, or are symbolic/hard links. Enforce an extracted-size limit.
6. Discover voicebank roots from actual `oto.ini` locations. Keep the original downloaded files unchanged.
7. Run the existing `axral_vocal_ai.voicebank_audit_cli` logic with root redaction. Keep detailed JSON reports local to the ephemeral runner.
8. Aggregate per-bank counts and issue codes into a sanitized summary that does not contain aliases, sample names, full paths, or audio.
9. Write a concise Markdown summary to `GITHUB_STEP_SUMMARY` and upload only sanitized JSON/Markdown summaries as an artifact.
10. Apply the configured fail threshold after all eligible banks have been examined, so one problematic bank does not hide findings from the others.

## Tests to add

- Hugging Face file-selection rules include relevant archives, `oto.ini`, `prefix.map`, and WAV files while excluding unrelated content.
- Download-size guard blocks unknown/over-limit content safely.
- ZIP and tar extraction reject traversal paths, absolute paths, and links.
- Voicebank discovery handles multiple/nested `oto.ini` locations without depending on a hard-coded dataset layout.
- Summary aggregation contains counts and issue codes only; no aliases, WAV paths, or local root paths.
- The workflow script remains importable/testable without network access.
- Existing test suite remains green on Python 3.10 and 3.12.

## Acceptance criteria

- A maintainer can manually launch a run against `SEKOIA2900/VO-US` without editing workflow code.
- A manual run stops before checkout/download unless `permission_reviewed=yes` is selected after the operator verifies hosted-processing permission for every selected voicebank.
- The workflow uses an immutable dataset commit for each run and records its SHA.
- At least one UTAU voicebank is audited when the dataset exposes eligible content; if no eligible files or `oto.ini` are found, the run fails clearly rather than reporting a false pass.
- Audit errors/warnings are visible in the sanitized summary and the configured threshold controls the final status.
- No voicebank WAVs, raw metadata, credentials, full aliases, or detailed parser reports are uploaded as workflow artifacts.
- The existing renderer and audio-processing paths are untouched.

## Non-goals

- Training or fine-tuning a singing voice model.
- Generating pitch or expression labels from WAV files.
- Changing VO-SE_vocal rendering behavior.
- Redistributing source voicebanks or committing them to this repository.
- Declaring a bank fully render-compatible based only on a filesystem audit; resolver comparison and listening checks remain separate gates.

## Implementation order

1. Commit this plan to the new work branch before implementation.
2. Add a network-independent Hugging Face selection/download/extraction/audit script.
3. Add focused unit tests for file selection, archive safety, discovery, and summary redaction.
4. Add the separate GitHub Actions manual workflow with a default-deny hosted-processing review gate.
5. Run the complete existing test suite and inspect CI results.
6. Update this plan with implementation status and open limitations before opening the pull request.


## Implementation status (2026-11-11)

### Completed on this branch

- [x] Commit this plan before implementation.
- [x] Add `scripts/audit_hf_voicebanks.py` for Hugging Face revision pinning, file selection, bounded downloads, safe extraction, dynamic voicebank discovery, audit aggregation, and sanitized reporting.
- [x] Add tests for Hub file selection, pre-download path filtering, unknown-size and download-limit rejection, archive path traversal/link/special-file rejection, extraction-size limits, common tar `./` root directory entries, nested voicebank discovery, symlink directory skipping, and report redaction.
- [x] Enforce the actual decompressed byte count while streaming archive members, rather than trusting archive size headers alone.
- [x] Add `.github/workflows/hf-utau-voicebank-audit.yml` with manual dispatch and an explicit per-voicebank hosted-processing permission acknowledgement; keep the workflow manual-only until terms are reviewed.
- [x] Keep the existing per-PR unit/integration workflow separate and unchanged.
- [x] Document workflow operation and data-use boundaries in `docs/real_voicebank_validation.md`.
- [x] Validate dataset IDs and requested Hub revisions before any Hub request or Markdown summary rendering; reject control characters, malformed path components, and oversized refs.
- [x] Require the Hub API's resolved revision to be a full 40-character hexadecimal commit SHA before file listing/download; record it in lowercase.
- [x] Aggregate archive failures by stable error code without exposing archive paths.
- [x] Detect U+FFFD replacement characters and conservative UTF-8/CP932 mojibake signatures in `oto.ini` and `prefix.map`; preserve source text and publish only aggregate issue-code counts.
- [x] Add tests for both metadata formats, normal Japanese false-positive resistance, and path-free audit summary output.
- [x] Publish validated per-bank audit issue-code aggregates in the Actions Markdown step summary, including `metadata_replacement_character` and `metadata_suspected_mojibake`, without exposing source paths or aliases.
- [x] Verify `fail_on: error`, `fail_on: warning`, and `fail_on: never` behavior with an end-to-end mocked Hub audit test.
- [x] CI green after the permission-register/workflow-gate updates: latest matrix run passed 621 tests in each job on Python 3.10 and Python 3.12 ([run 43378470640](https://github.com/nebula-INE/Axral_vocal_AI/actions/runs/43378470640)).
- [x] Migrate repository workflow actions to Node.js 24-compatible v7 releases and pin each action to its verified full commit SHA. Keep the human-readable v7 tag in a YAML comment:
  - `actions/checkout`: `3d3c42e5aac5ba805825da76410c181273ba90b1`
  - `actions/setup-node`: `949feb2413d6458794dcd2491c4babbbce0c15c1`
  - `actions/setup-python`: `6d4fd22b20465ccc0f7354476588e8df7c9ca0e0`
  - `actions/upload-artifact`: `cf430e030ddbb5b0abf93d22962f4752f3646cd9`
- [x] Add regression tests that require every `uses:` reference in the affected workflows to be a full 40-character commit SHA.
- [x] Restrict the shared PR test workflow token to `contents: read`; set `persist-credentials: false` on both checkout steps.
- [x] Keep the hosted audit workflow at `contents: read` and disable checkout credential persistence there as well.
- [x] Verify the latest CI runs after action pinning and least-privilege updates: Python 3.10 and 3.12 both passed 623 tests ([run 43434211223](https://github.com/nebula-INE/Axral_vocal_AI/actions/runs/43434211223)).
- [x] Verify both Python matrix jobs after the earlier v7 migration; no Node.js 20 deprecation warning appeared in the updated test workflow logs.

### Remaining verification

- [ ] Run the workflow against the live `SEKOIA2900/VO-US` Hub repository and confirm its actual repository layout, file types, total selected size, and number of discoverable voicebank roots.
- [x] Add a pre-download Hub path filter so a maintainer can reduce the amount fetched before snapshot download.
- [ ] Review the live sanitized report and adjust limits or file-selection rules only if the dataset contents require it.

The live Hub download has not yet been executed from this development session. The current session cannot dispatch a workflow run, and the public Hub tree could not be fetched from this runtime. The workflow and script are covered by CI, but actual `VO-US` file layout, selected size, and voicebank count remain unverified until a maintainer runs the workflow after merging this PR. The implementation resolves the requested revision and discovers file paths dynamically at workflow runtime; this is not a claimed live-data pass.

### Current archive support and bounds

- Supported archives: ZIP (including UAR when ZIP-compatible) and tar/tar.gz/tar.bz2/tar.xz/tgz/tbz2/txz.
- RAR and 7z are not currently supported.
- Default limits are 4096 MiB selected download and 8192 MiB extracted archive contents; maintainers can adjust these through manual workflow inputs.
- `file_path_filter` is applied to Hub paths before download; `voicebank_filter` is applied to discovered roots after download.
- Only aggregate counts and issue codes are uploaded. Raw audio, detailed parser reports, aliases, and sample filenames are not workflow artifacts.
- The workflow performs technical auditing only. It does not infer or grant permission for machine-learning training or redistribution.
### Permission governance hardening (2026-11-13)

- [x] Add a public, blank-safe starter permission register template for the four initial voicebank research candidates. All release and permission decisions start as `review_required`; no license approval is inferred.
- [x] Extend the validation guide with separate local processing, hosted processing, feature extraction, ML training, model distribution, and audio redistribution scopes.
- [x] Make the Hugging Face Actions workflow manual-only. Remove the weekly schedule until per-bank hosted-processing permissions have been recorded.
- [x] Add required `permission_reviewed` input (default `no`) and fail before checkout or Hub access unless the operator explicitly confirms that every selected bank permits hosted processing on GitHub Actions.
- [x] Keep the optional Hugging Face token scoped to the actual download/audit step, after the permission gate.
- [ ] Run a live audit only after the selected banks' exact terms and hosted-processing decisions are recorded. The current session has not verified the live Hugging Face repository layout or those permissions.


## Kaggle credential-scope hardening (2026-11-14)

- [x] Code review found that the notebook previously assigned `HF_TOKEN` to the kernel-wide `os.environ`, causing later subprocesses to inherit the Hub credential.
- [x] In PR [#65](https://github.com/nebula-INE/Axral_vocal_AI/pull/65), keep the token out of the notebook kernel environment and strip it from default child-process environments.
- [x] Pass the optional `HF_TOKEN` only through the explicit environment of `scripts/kaggle_hf_download.py`; unrelated package installation, pytest, audit and training subprocesses do not inherit it.
- [x] Add a behavioral regression test for default token stripping and explicitly scoped pass-through, plus a notebook wiring assertion.
- [x] Initial PR CI passed on Python 3.10 and 3.12 (**742 tests each**, run [43559386138](https://github.com/nebula-INE/Axral_vocal_AI/actions/runs/43559386138)). Any subsequent commit to this PR must pass the matrix again before merge.
- [ ] Merge only after the PR's final CI and review are complete.


---

## Universal singing model research and development plan (2026-11-24)

> Status: architecture and research direction only. The items in this section are proposed work, not claims that a universal singing model, human-singing training pipeline, or AI audio generator has already been implemented.

### Product objective

Build one shared Axral singing model that can use different UTAU voicebanks and produce natural, human-like singing while retaining each voicebank's recognizable vocal characteristics.

The model must aim to generalize to voicebanks that were not present in its training set. Creating and maintaining a separate model for every UTAU voicebank is not the target.

The long-term model should learn or generate:

- Natural pitch movement and transitions between notes.
- Note timing, consonant and vowel transitions, and phoneme duration.
- Dynamics, accents, phrasing, and expressive intensity.
- Vibrato onset, depth, rate, and variation.
- Breath-like phrasing and other appropriate vocal-expression changes.
- Voicebank-dependent behavior across phonemes, pitches, and registers.

A pitch-delta predictor alone is not sufficient to satisfy this product objective. It may be useful as an initial experiment or one component, but it must not be described as the completed universal singing model.

### Non-negotiable engine and compatibility requirements

- Preserve the existing WORLD synthesis path as a supported synthesis engine.
- Do not replace WORLD with AI, remove WORLD-only operation, or casually change the existing rendering, export, volume, noise, or post-processing behavior.
- Treat the AI singing model as an additional engine. The model is to be loaded and invoked from the VO-SE C++ core through a defined model/runtime interface in vo-se_core.cpp.
- Keep AI model inference separate from the existing WORLD implementation so that AI development does not destabilize the current renderer.
- Keep BigVGAN's role distinct: it is an acoustic/vocoder component, not the model responsible for understanding a score and deciding human-like singing expression.
- The intended product modes are:
  1. WORLD: existing synthesis behavior.
  2. AI: neural singing generation when a suitable model is available.
  3. Hybrid: AI predicts singing controls or acoustic features and the existing renderer produces the audio.
- Start Hybrid experiments by predicting control information for the existing renderer (for example F0, timing, dynamics, and vibrato). Do not begin by mixing unvalidated AI waveforms into the current output path.
- AI model loading or inference failures must not break WORLD-only operation. Any fallback from a requested AI mode must be explicit and reported; do not silently present WORLD output as successful AI output.
- Establish regression tests for WORLD-only output before integration. Existing high-quality WAV export behavior is a protected baseline.

### Training-data strategy

Real human singing data is important for learning natural singing behavior. UTAU voicebank recordings alone can teach voicebank and phoneme characteristics, but they do not provide reliable ground truth for how a human singer naturally phrases, articulates, breathes, or expresses a melody.

Axral does not need to record a large singing corpus from scratch as the first step. Prefer a staged combination of datasets whose source, license, and permitted processing have been checked.

Use distinct data roles:

| Data source | Intended learning signal | Important limitation |
| --- | --- | --- |
| UTAU voicebank recordings and metadata (oto.ini, prefix.map, aliases, pitch/range information) | Voice characteristics, phoneme coverage, pronunciation behavior, and voicebank-specific conditioning | Does not by itself teach natural human singing expression |
| Human singing recordings paired with score, lyrics, phonemes, and alignment | Natural phrasing, pitch behavior, timing, dynamics, vibrato, and expression | Alignment and rights must be verified; recordings without suitable labels may require preprocessing |
| Controlled UTAU-generated singing examples | Broad coverage of voicebanks, phonemes, notes, tempos, and controlled input/output pairs | Synthetic data inherits the source renderer's behavior and cannot replace real human-singing supervision |
| Carefully licensed auxiliary speech/singing or vocal-technique data | Supplemental phonetic, acoustic, or vocal-technique coverage | Use only for the specific task and rights actually permitted |

Human-singing data should be prioritized when it has reliable alignment between audio and musical/phonetic information. Useful annotations include score or MIDI, lyrics, phoneme sequence, phoneme boundaries, note boundaries, F0, timing, and singer/session metadata where licensing permits.

Candidate corpora for investigation include PJS, GTSinger, M4Singer, VocalSet / Annotated-VocalSet, and Vocadito. They are candidates for research and pipeline evaluation, not pre-approved training sources. Verify the current dataset license, original recording rights, attribution/share-alike obligations, non-commercial restrictions, hosted-processing terms, derivative-model rights, and model-weight distribution rights separately for each source. In particular, do not use a research-only or non-commercial corpus to train a commercial Axral model unless separate permission explicitly allows it.

### Permission and provenance gates

Before any dataset is used, record its provenance and permission status. Public download availability is not evidence of permission for AI training or commercial use.

Track these permissions separately for every selected dataset or voicebank:

- Local download and inspection.
- Hosted processing (including Kaggle and CI runners).
- Feature extraction and derived annotations.
- Machine-learning training and evaluation.
- Commercial use of the resulting model.
- Distribution of model weights or checkpoints.
- Redistribution or delivery of source audio.

Keep the existing default-deny hosted-processing gate and voicebank permission register. Extend governance as needed for human-singing corpora; a voicebank approval must not be treated as approval for an unrelated singing corpus. Never place source audio, private labels, credentials, or unapproved dataset contents in repository history or CI artifacts.

### Proposed model responsibilities and interfaces

The preferred direction is one deployable shared model with clearly defined internal responsibilities. The following are logical components of the model pipeline, not a requirement to train a separate model per voicebank:

1. **Universal voicebank representation**: encode the selected voicebank's usable characteristics from its recordings and metadata. Support different UTAU recording styles and phoneme systems without assuming one fixed alias convention.
2. **Singing performance prediction**: combine score, lyrics/phonemes, voicebank representation, and expression controls to predict natural performance information. Initial targets may include F0 contours, phoneme/note timing, dynamics, and vibrato parameters.
3. **Optional acoustic generation**: after the control-prediction stage is validated, investigate generating acoustic features and/or waveform audio for AI mode.

Define a versioned input/output contract before training or C++ integration. At minimum, document sample rate, frame hop, feature dimensions, pitch units, time units, phoneme encoding, voicebank conditioning format, normalization, tensor shapes, model metadata, and supported runtime/ONNX opset. Validate shapes, finite values, ranges, model version, and compatibility at load/inference time.

The Python research/training pipeline and the C++ inference interface must share test fixtures and a documented contract. Do not assume that a Python prototype is automatically suitable for real-time or offline C++ inference.

### Development phases and acceptance gates

#### Phase 0 — Research and data readiness

- [ ] Inventory candidate human-singing corpora and UTAU voicebank sources.
- [ ] Create a per-source provenance and permission register covering all scopes listed above.
- [ ] Confirm which sources may be used for hosted preprocessing, research training, commercial training, and model-weight distribution.
- [ ] Define a common data manifest for audio, score, lyrics, phonemes, alignments, voicebank metadata, and split/group identifiers.
- [ ] Define train/validation/test splits by singer and by voicebank to prevent leakage into the unseen-voicebank evaluation.
- [ ] Decide which tasks can be learned from existing labels and which require alignment or annotation work.

**Gate:** no hosted processing or training begins for a source until its required permission checks are recorded. No corpus is designated as commercially usable based only on public availability.

#### Phase 1 — Voicebank representation baseline

- [ ] Build a reproducible feature-extraction path for supported UTAU formats, including CV, VCV, CVVC, aliases, multipitch information, oto.ini, and prefix.map.
- [ ] Preserve original source metadata and report parsing uncertainty rather than silently guessing aliases or paths.
- [ ] Produce a consistent voicebank representation and test it across multiple structurally different voicebanks.
- [ ] Verify that voicebanks excluded from training can still be encoded without per-bank model fine-tuning.

**Gate:** the same model interface can accept multiple supported voicebanks, with clear diagnostics for unsupported or incomplete data.

#### Phase 2 — Human-singing supervision and performance model

- [ ] Prepare a small, rights-cleared pilot set of aligned human singing examples before scaling dataset collection.
- [ ] Establish a baseline for score/phoneme-to-performance prediction.
- [ ] Train and evaluate natural F0, timing, dynamics, and vibrato predictions separately before combining them.
- [ ] Compare predicted controls with held-out human singing references and perform listening evaluations.
- [ ] Use UTAU-generated examples for controlled coverage and augmentation, while explicitly measuring the gap between synthetic and human-singing supervision.

**Gate:** demonstrate measurable improvement over simple rule-based or unconditioned baselines on singers and songs excluded from training. Do not claim human-like singing from pitch accuracy alone.

#### Phase 3 — Unseen voicebank generalization

- [ ] Hold out complete voicebanks from training, not merely random utterances from the same banks.
- [ ] Test CV/VCV/CVVC, alias variants, multipitch banks, different pitch ranges, and incomplete metadata.
- [ ] Evaluate voicebank identity preservation, intelligibility, phoneme transitions, pitch/timing accuracy, and listening quality.
- [ ] Record which voicebank types fail and whether the issue comes from parsing, insufficient phoneme coverage, representation, or model generalization.
- [ ] Avoid per-voicebank fine-tuning as a hidden requirement for passing the universal-model gate.

**Gate:** a previously unseen, supported voicebank can be used through the common interface without training a dedicated model for that bank. Document limitations rather than claiming universal compatibility prematurely.

#### Phase 4 — WORLD Hybrid integration

- [ ] Define the versioned model interface consumed by vo-se_core.cpp.
- [ ] Export a small validated model to the selected inference format and verify numerical parity between Python and C++.
- [ ] Feed AI-predicted controls into a separate Hybrid path while preserving the original WORLD path.
- [ ] Add explicit engine selection, model-load diagnostics, inference errors, and status reporting.
- [ ] Confirm WORLD-only regression tests and WAV export checks remain unchanged.
- [ ] Compare WORLD baseline and Hybrid results on identical UST/score, voicebank, and settings.

**Gate:** AI/Hybrid integration does not alter WORLD-only behavior, and model failure cannot disable WORLD synthesis.

#### Phase 5 — AI acoustic generation

- [ ] Only after the performance-control model and unseen-voicebank evaluation are credible, select and train an acoustic generation approach.
- [ ] Evaluate acoustic-feature generation and vocoder options independently from singing-expression prediction.
- [ ] Compare AI output with the WORLD baseline for intelligibility, naturalness, artifacts, latency, and reproducibility.
- [ ] Keep AI synthesis optional until quality and runtime requirements are met.

**Gate:** AI mode must meet documented quality and stability criteria before being treated as a production alternative to WORLD.

### Evaluation protocol

Evaluate the system at multiple levels rather than relying on a single aggregate score:

- **Data/compatibility:** manifest validity, audio integrity, phoneme coverage, alignment quality, and metadata parse success.
- **Performance prediction:** F0 contour error, note transition behavior, onset/offset timing, phoneme duration, dynamics, and vibrato parameters.
- **Generalization:** complete held-out singers, songs, and voicebanks; report results by voicebank type and phoneme coverage.
- **Audio quality:** intelligibility, naturalness, artifacts, voicebank-character preservation, and listening-test results.
- **Engineering:** deterministic inference where expected, model load validation, memory/runtime cost, C++/Python parity, and WORLD regression results.

Keep objective metrics and listening evaluations separate. A low F0 error does not prove natural singing, and an attractive sample from a training voicebank does not prove unseen-voicebank generalization.

### Immediate next work

1. [ ] Audit current Axral_vocal_AI training and inference code to distinguish real model behavior from prototype, placeholder, or metadata-only prediction paths.
2. [ ] Review the existing permission register and validation documentation; add human-singing dataset entries only after source-specific terms have been checked.
3. [ ] Produce a dataset feasibility matrix for the candidate corpora: language, singer count, duration, annotation/alignment fields, license, commercial-training status, hosted-processing status, and missing labels.
4. [ ] Define the first pilot manifest and versioned feature/label schema.
5. [ ] Run a small end-to-end data preparation and baseline experiment before committing to a large model architecture or expensive training run.
6. [ ] Keep WORLD changes out of this repository's AI research milestones; track VO-SE C++ integration as a separate, gated workstream.

### Current status and limitations

- This section records the agreed product direction and proposed work only.
- Existing voicebank audit and permission-gating work remains a data-governance foundation; it is not evidence that human-singing supervision or a universal singing model is ready.
- Existing F0-delta or metadata-based experiments are prototypes and must be evaluated against the broader objective above.
- No candidate corpus is pre-approved for commercial model training by this plan.
- No large-scale human-singing dataset collection, universal-model training result, unseen-voicebank success, or AI audio-generation quality result is claimed here.
- The immediate milestone is a permission-cleared, reproducible pilot dataset and a small baseline that can be measured on held-out singers and voicebanks.
