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


---

## Free commercial-use dataset catalog and zero-budget adoption plan (2026-11-25)

> Scope: a solo student/indie-developer workflow with no dataset budget and no expectation of negotiating individual paid licenses. The catalog is a research shortlist, not legal advice or proof that every third-party right is cleared. No dataset is automatically approved for model training merely because it is downloadable.

### Adoption rules

1. Prefer datasets whose published terms explicitly permit commercial singing-voice-synthesis (SVS) training, or whose declared license is a permissive commercial license such as CC BY 4.0 / CC0 1.0.
2. Keep datasets with CC BY-SA 4.0 or custom restrictions in a separate data group. Commercial use may be allowed, but attribution, share-alike, model-release, parallel-training, voice-identity, and raw-audio redistribution clauses must be followed. Do not combine them into a production checkpoint until the model-distribution implications have been reviewed.
3. Do not use NC, ND, research-only, or unclear-license sources for commercial-model training. Do not solve an unclear license by assuming that a research paper, GitHub mirror, or third-party dataset index overrides the original rights.
4. A dataset license only covers rights the provider can grant. Check the source record and included LICENSE/NOTICE, plus recording, composition, lyrics, arrangement, and performer permissions where applicable. If the musical-work rights are unclear, do not use that recording in the commercial corpus.
5. Do not redistribute source audio. Keep source data outside Git history, release packages, public CI artifacts, and public Kaggle outputs. Record URLs, exact revision/version, retrieval date, file hashes, license text/hash, attribution, and permitted-use scopes in the dataset manifest.
6. No paid acquisition or private negotiation is assumed by this plan. If a candidate requires written permission not already granted by its public terms, mark it `hold_no_contact` and do not train on it.

### Candidate catalog

The following catalog separates singing supervision from speech/phonetic support. The priority is based on fit to Axral's universal shared-model objective, not just hours of audio.

| ID | Dataset and source URL | Public terms / commercial position | Content and best Axral use | Decision |
| --- | --- | --- | --- | --- |
| D01 | [Lem the Shapeshifter — organic singing corpus](https://huggingface.co/datasets/wik-wav/lem-singing-corpus) | Dataset card/declared LICENSE reports CC BY 4.0. The separate [synthetic range-extension dataset](https://huggingface.co/datasets/wik-wav/lem-singing-corpus-synthetic) is CC BY-NC-SA 4.0 and is excluded. The Lem voicebank/character terms are a separate layer if the model is presented as Lem. | English and Japanese phoneme/reclist material with aligned singing annotations; useful for phoneme coverage, note/phoneme alignment, and first end-to-end training preparation. The Japanese material is phoneme/reclist coverage, not natural Japanese sentences. Limited voice identity diversity. | **P1 candidate.** Use only the organic repository. Snapshot its CC BY 4.0 LICENSE and verify recording/composition provenance and character-term boundaries before training. Never merge the synthetic repository. |
| D02 | [VocalSet — Zenodo 1193957](https://zenodo.org/records/1193957) | Listed as CC BY 4.0 in public singing-dataset indexes. Re-check the live Zenodo license metadata and the downloaded archive's notices before training. | 10.1 hours, 20 professional singers, all five vowels, standard and extended vocal techniques; useful for voice diversity, vowels, sustained notes, and expressive/vocal-technique features. About 2.1 GB. Not a score/lyrics-aligned corpus. | **P1 candidate.** Strong general singing-expression auxiliary set after the exact license/NOTICE is captured. |
| D03 | [vocadito — Zenodo 5578807](https://zenodo.org/records/5578807) | Public dataset references identify CC BY 4.0; verify the exact record metadata and archive notices at retrieval. | 40 short monophonic solo-singing excerpts in seven languages; frame-level F0, two note-annotation versions, lyrics, and language labels. About 58.5 MB. Excellent small baseline/evaluation set, not a large training corpus. | **P1 candidate.** First download for pipeline smoke tests after license snapshot. |
| D04 | [Choral Singing Dataset — Zenodo 2649950](https://zenodo.org/records/2649950) | Listed as CC BY 4.0 in dataset/tool indexes; confirm the current Zenodo record and archive LICENSE/README before training. Do not confuse this with the unrelated Children's Song Dataset (CSD), which is non-commercial. | 16 individual singers, three a cappella pieces, individual vocal tracks, frame-wise F0, note annotations, and semi-synchronized MIDI; about 1.1 GB. Useful for multi-singer pitch/intonation and note-conditioning. Choral repertoire is not equivalent to pop solo singing. | **P1/P2 candidate.** High value for F0/score alignment and singer hold-out testing. |
| D05 | [Dagstuhl ChoirSet — Zenodo 4608395](https://zenodo.org/records/4608395) | Listed as CC BY 4.0 by public corpus indexes; verify the live record license and archive notices before use. | About 5.1 GB; amateur ensemble, choir and quartet settings, multitrack close-up microphones for individual singers. Useful for choir/individual-voice separation, F0, intonation, and robust acoustic evaluation; only two choir pieces, so avoid overfitting. | **P2 candidate.** Useful auxiliary/evaluation corpus rather than primary solo-SVS supervision. |
| D06 | [Jingju a Cappella Recordings Collection (JaCRC) — Zenodo 6536490](https://zenodo.org/records/6536490) | Dataset catalog lists CC BY 4.0. The collection includes 53 recordings originating from earlier sources; do not automatically assume those 53 inherit the collection's rights. | 314 vocal recordings in the collection; most were newly created for it. Manual segmentation for 217 recordings, lyrics for 156, and score-line alignment for a subset. Useful for ornamentation, expressive pitch movement, and non-Western vocal technique. Genre-specific Jingju singing. | **P2 conditional.** Use only recordings whose provenance is clearly within the collection's grant; exclude the 53 pre-existing-source recordings unless their own rights are independently clear. |
| D07 | [ViCa — GitHub](https://github.com/apleGitHub/ViCa) | CC BY 4.0 plus explicit Terms of Use: permits multispeaker SVS training and commercial SVS training; raw-audio redistribution is prohibited. Multispeaker training is prohibited when any other included vocalist lacks AI-training permission. It also prohibits SVC/voice-conversion use and public release of a standalone model of this voice. | Vietnamese singing corpus with DiffSinger-compatible labels/phoneme inventory. Valuable as a clearly stated commercial-SVS example and language-phoneme coverage. It is one voice provider, not broad multi-singer diversity. | **P1 conditional candidate.** Respect the extra Terms of Use in addition to CC BY 4.0; use only in an SVS multi-speaker context whose other speakers are also cleared. No raw data mirroring. |
| D08 | [LIEE Filipino Singing Corpus — GitHub](https://github.com/julieraptor/LIEE-Filipino-Singing-Corpus-for-Singing-Voice-Synthesis) | Free public terms explicitly allow use as parallel training material for DiffSinger and other SVS databases (including NNSVS/ENUNU), and commercial distribution of vocal-synthesis databases created using it as parallel material, with credit. Raw-file redistribution and publishing a LIEE-specific clone/version without written permission are prohibited. | About 17 min 40 sec, 44.1 kHz/16-bit, WAV + LAB + DS; Filipino singing and labels. Useful as multilingual phoneme and parallel-training supplementation, not a large corpus. | **P1 conditional candidate.** Use only as the stated parallel-learning material and credit LIEE. Do not release its raw files or a LIEE voice-specific model. |
| D09 | [ACV-001 — GitHub](https://github.com/Archivoice/ACV-001) | CC BY-SA 4.0 for direct use and models mainly featuring this voice. The author states that this license does not apply to models trained via parallel training and that supplementary use may follow the resulting model's own license. Attribution remains required. | Multilingual labeled singing: Cantonese, Mandarin, English, Japanese via romaji, Korean, and Taiwanese; WAV/LAB and DiffSinger-oriented annotations. The English slur/pitch annotations have a documented quality warning. | **P2 parallel-only candidate.** Use only as supplemental/parallel data, never as a dedicated ACV-001 voice model. Filter or re-audit the English section. |
| D10 | [ACV-002 — GitHub](https://github.com/Archivoice/ACV-002) | CC BY-SA 4.0 with the same stated parallel-training exception as ACV-001. | A second vocal presentation from the same voice provider, with Mandarin and English labels, phonation/exhale/vocal-fry labels, WAV/LAB and DS annotations. It is not an independent additional singer. | **P2 parallel-only candidate.** Same conditions as D09; do not count it as a new independent singer. |
| D11 | [ACV-003 — GitHub](https://github.com/Archivoice/ACV-003) | CC BY-SA 4.0 with the same stated parallel-training exception as ACV-001. | Peking-opera singing with manually corrected labels, WAV/LAB and DS annotations including F0/note-slur data. Same voice provider as ACV-001/002. | **P2 parallel-only candidate.** Useful for genre/ornamentation coverage, not speaker-count expansion. |
| D12 | [PJS — Phoneme-balanced Japanese Singing Voice Corpus](https://sites.google.com/site/shinnosuketakamichi/research-topics/pjs_corpus) | CC BY-SA 4.0. Commercial use is not excluded by the NC term (there is none), but attribution/share-alike obligations remain. The effect on proprietary model weights must be reviewed before inclusion in a closed commercial release. | Japanese phoneme-balanced singing material with score/MIDI/MusicXML and phoneme-oriented design. Strong Japanese phoneme coverage; not a large multi-singer corpus. | **P2 conditional / isolated data group.** Do not mix into production weights until share-alike/model distribution handling is documented. |
| D13 | [Mozilla Common Voice — Japanese dataset catalog](https://commonvoice.mozilla.org/ja/datasets) | The catalog lists Japanese Scripted Speech 27.0 under CC0-1.0. Use the exact selected version and retain its dataset card/metadata. | Read speech, not singing. Japanese pronunciation/phoneme and speech-side auxiliary work only; it cannot teach singing phrasing, vibrato, or score-to-song mapping. Japanese v27 is listed at about 14.36 GB. | **Speech-only auxiliary.** Keep in a separate speech manifest and separate task; do not present it as singing supervision. |

### Known blocked or excluded sources

| Dataset | Publicly visible restriction / reason | Action |
| --- | --- | --- |
| [GTSinger](https://huggingface.co/datasets/GTSinger/GTSinger) | CC BY-NC-SA 4.0 (NonCommercial). | Exclude from all Axral commercial-model training and product validation datasets. |
| [M4Singer](https://github.com/M4Singer/M4Singer) | CC BY-NC-SA 4.0 (NonCommercial). | Exclude. |
| [OpenCPOP](https://wenet.org.cn/opencpop/) | CC BY-NC-ND / restrictive terms reported for the corpus; ND is unsuitable for model-training derivatives without clear permission. | Exclude unless the original terms are changed by the rights holder. |
| [JSUT-song](https://sites.google.com/site/shinnosuketakamichi/research-topics/jsut) | Published comparison reports CC BY-NC-ND. | Exclude. |
| [NUS-48E](https://huggingface.co/datasets/guey-khala-mari/NUS-48E) | Research-only terms; dataset card/README explicitly says research use only. | Exclude from commercial training. |
| [Singing Voice Audio Dataset (Isophonics)](https://isophonics.net/SingingVoiceDataset.html) | CC BY-NC-SA. | Exclude. |
| [Children's Song Dataset (CSD)](https://zenodo.org/records/1319597) | CC BY-NC-SA according to public SVS dataset indexes. This is not the Choral Singing Dataset D04. | Exclude. |
| [Project AI❤dol Public English Dataset](https://github.com/lottev1991/Project-AIdol-Public-English-Dataset) | CC BY-SA 4.0; its terms ask that models featuring the voice not be publicly released without prior permission. | `hold_no_contact`; do not use in a public commercial model absent the permission the author requires. |
| [NIT-SONG070-F001](https://sinsy.sourceforge.net/readme_hts_voice_nitech_jp_song070_f001.php) | A paper/source describes the license only generically as "CC"; the exact license and commercial model-weight permissions were not established in this review. | `hold_license_unclear`; do not train until an exact license file and rights scope are verified. |
| [Lem synthetic range extension](https://huggingface.co/datasets/wik-wav/lem-singing-corpus-synthetic) | CC BY-NC-SA 4.0, explicitly non-commercial. | Exclude; use only D01's organic source corpus if approved. |
| [Alex Floarea 2.0 / CSD / other MakeDiffSinger candidates](https://github.com/openvpi/MakeDiffSinger/wiki/Public-datasets) | The public dataset index marks several as CC BY-NC or CC BY-NC-SA, or custom terms not cleared for this no-contact plan. | Check individually; never bulk-download/train from the index. |

### Data grouping and manifest requirements

Do not merge all sources into one undifferentiated dataset. Create separate manifests and dataset groups:

- `commercial_cc_by_cc0/`: sources with a captured CC BY 4.0 / CC0 1.0 record and a completed source/provenance review (initial targets D01-D06 and D13, but only after their exact source files and rights are checked).
- `commercial_custom_terms/`: explicit SVS commercial-use sources with extra constraints (D07-D08).
- `parallel_training_sharealike/`: D09-D11. Keep separated and enforce each source's parallel-training exception and attribution.
- `sharealike_review_required/`: D12 PJS. Keep out of production checkpoints until model-distribution implications are resolved.
- `speech_auxiliary/`: D13 Common Voice speech. Do not use as singing waveform targets.
- `blocked/`: all NC, ND, research-only, unclear, or permission-required sources.

Each manifest entry must include:
`dataset_id`, `canonical_url`, `version_or_commit`, `retrieved_at`, `archive_sha256`, `license_id`, `license_url`, `license_text_sha256`, `attribution_text`, `commercial_svs_allowed`, `parallel_training_only`, `model_weights_distribution_allowed`, `raw_audio_redistribution_allowed`, `hosted_processing_allowed`, `third_party_composition_status`, `performer_rights_status`, `provenance_notes`, and `decision`.

Allowed decision values:
- `review_required`: not yet inspected or captured.
- `approved_local_pilot`: source and scope approved for local-only pilot processing.
- `approved_hosted_pilot`: hosted processing separately approved.
- `approved_commercial_svs_training`: all relevant source, performer, composition, and training permissions documented.
- `approved_parallel_only`: only the precise parallel-training use described by the source terms is approved.
- `hold_no_contact`: requires private/written permission not available under this plan.
- `hold_license_unclear`: exact license or source provenance unresolved.
- `blocked_noncommercial`: NC/research-only restriction.
- `blocked_no_derivatives`: ND restriction or incompatible derivative restriction.

The manifest must default every newly added source to `review_required`. A public license badge alone must never set a permission field to true. Keep hosted-processing permission separate from local processing and commercial-training permission. The existing Hugging Face voicebank audit workflow's default-deny gate remains in force; approval of a voicebank never approves a human-singing dataset.

### Zero-budget download and execution order

1. **Small smoke-test set:** D03 vocadito first (about 58.5 MB) to validate audio loading, F0, note, lyric, and split code without spending storage or GPU time.
2. **Phoneme/alignment pilot:** D01 organic Lem corpus after capturing its CC BY 4.0 license and recording/song provenance. Never use its synthetic NC-SA sibling.
3. **Vocal-expression pilot:** D02 VocalSet after archiving the exact license and notices. Use for voice-technique and acoustic representation tasks, not fake score alignment.
4. **Multi-singer/F0 evaluation:** D04 Choral Singing Dataset. Then D05 Dagstuhl ChoirSet if disk/compute limits permit.
5. **Commercially permitted custom SVS augmentation:** D07 ViCa and D08 LIEE only with their explicit multi-speaker/parallel-training restrictions enforced.
6. **Genre and parallel-training expansion:** D06 JaCRC clean-provenance subset and D09-D11 ACV sources. Maintain per-source groups and attribution.
7. **Japanese-specific coverage:** D12 PJS only in its isolated share-alike group until checkpoint terms are settled; use D13 Common Voice solely for speech/phonetic auxiliary tasks.
8. Before any large training run, calculate storage and compute budgets from selected manifests. Do not automatically download every candidate. The initial target is a small reproducible data-preparation pilot, not a production-scale model.

### Required dataset evaluation work

- [ ] Create `datasets/manifests/` entries for D01-D13 with all new records defaulting to `review_required`.
- [ ] Save a source/license snapshot for every candidate: dataset-card/README, LICENSE/NOTICE, terms, version/revision, and SHA-256. Do not rely on a mutable `main` branch without recording its commit.
- [ ] Re-check the exact CC license metadata for Zenodo records D02-D06 at retrieval time; their record pages and public corpus indexes may expose license metadata differently. Keep them on hold until the archive and record agree.
- [ ] Verify Lem D01's organic dataset and separate its NC-SA synthetic sibling at the file-selection layer, not merely by operator convention.
- [ ] Verify the composition/lyrics and recording provenance of the songs in every singing corpus. CC BY on a corpus page does not prove every underlying composition or included third-party recording is covered.
- [ ] Add license-scope unit tests that reject NC, ND, research-only, unknown, and unreviewed entries from the commercial-training manifest.
- [ ] Add group-isolation tests so `parallel_training_sharealike/`, `sharealike_review_required/`, and `speech_auxiliary/` cannot be silently merged into the clean commercial group.
- [ ] Add a report that states, per dataset, what can be used for local inspection, hosted preprocessing, feature extraction, commercial SVS training, model-weight distribution, and raw-audio redistribution.
- [ ] Run the first pilot locally or in a separately approved runtime. No source audio or detailed labels may be uploaded to CI artifacts or committed to GitHub.
- [ ] Keep the held-out split grouped by singer, song, and voicebank. For the universal-model test, reserve complete singers and complete voicebanks that do not appear in training.

### Current decision

- The best zero-budget starting combination is **vocadito + organic Lem + VocalSet**, followed by the 16-singer Choral Singing Dataset. This combination provides a manageable first pass across F0/notes/lyrics, phoneme alignment, singing technique, and multiple singers.
- The best explicitly stated custom commercial-SVS supplements are **ViCa and LIEE**, but their use is restricted to the exact SVS/multispeaker/parallel-training purposes in their terms.
- **ACV-001/002/003** are possible parallel-training supplements, not three independent singers. Their CC BY-SA license and stated exception must remain attached to their manifest entries.
- PJS is valuable Japanese singing coverage but remains isolated because of CC BY-SA obligations. Common Voice is speech-only auxiliary data.
- No dataset is marked `approved_commercial_svs_training` by this plan update. Actual source versions, notices, and underlying recording/composition rights still need to be captured and reviewed before the first commercial training run.


---

## Canonical Hugging Face dataset repository: extend VO-US (2026-11-25)

### Repository decision

Use the existing Hugging Face Dataset repository [`SEKOIA2900/VO-US`](https://huggingface.co/datasets/SEKOIA2900/VO-US) as the canonical Axral data catalog and storage entry point. Do **not** create a second `axral-singing-datasets` repository unless storage, access control, or dataset-loader constraints later make separation necessary.

The repository already serves as the UTAU voicebank data location used by the voicebank audit workflow. Preserve its existing paths and files. Add new corpus areas alongside the existing voicebank data; do not move, rename, rewrite, or bulk-reupload the current VO-US contents as part of this change.

This is a repository-organization decision only. It does not grant permission to copy or redistribute any source corpus, does not change any source license, and does not mean the listed candidate datasets have been downloaded or approved.

### Required separation inside VO-US

Use the following as the **proposed additive layout**. Before creating directories, inspect the live repository tree and adapt names to its existing layout. Existing paths take precedence.

```text
VO-US/
├── README.md
├── voicebanks/                  # Existing UTAU source banks; preserve current paths
├── corpora/
│   ├── singing/
│   │   ├── commercial_cc_by_cc0/
│   │   ├── commercial_custom_terms/
│   │   ├── parallel_training_sharealike/
│   │   └── sharealike_review_required/
│   └── speech_auxiliary/
├── manifests/
│   ├── datasets.yaml
│   ├── permissions.yaml
│   ├── splits.yaml
│   └── checksums.sha256
├── licenses/
│   ├── source_records/
│   ├── license_snapshots/
│   └── attribution/
├── processed/
│   ├── audio_features/
│   ├── f0/
│   ├── phonemes/
│   ├── alignments/
│   └── expression_labels/
└── reports/
    ├── license_audit/
    └── dataset_audit/
```

Folder names are organizational labels, not permission states. A file can enter a source or processed folder only when the specific source terms permit that copy and processing. For candidates that do not permit raw-audio redistribution or private mirroring, store only metadata, canonical source URL, exact revision/version, license evidence references, and hashes; retrieve the source directly from its origin when permitted.

### Repository visibility and access gate

- [ ] Inspect current Hugging Face repository metadata and confirm whether `SEKOIA2900/VO-US` is public or private. The URL supplied in chat was not independently readable from this development session, so its current visibility is not asserted here.
- [ ] If it is public, do not upload restricted source audio or private-only materials. Keep it public only for content whose terms allow public distribution; otherwise make a deliberate visibility decision before any sensitive upload.
- [ ] If changing an existing public repository to private is considered, evaluate the impact on current consumers of VO-US first. Hugging Face documents that private repositories disappear from other users' search results and visitors without access receive a 404; this is a breaking access change.
- [ ] Confirm owner write access, current storage use/quota, and whether any collaborators or existing workflows depend on the repository's present layout.
- [ ] Keep tokens in local/Kaggle secret stores. Never commit a Hugging Face token, credential file, or signed download URL.

### Dataset-loader isolation

Because Hugging Face Datasets can automatically infer files and splits from repository structure, do not put all corpus audio under generic root-level `train/`, `test/`, `audio/`, or `data/` directories. Keep every dataset under its own source-specific path, and use explicit dataset-card `configs` / `data_files` only for formats intended to be loaded by `datasets.load_dataset()`.

Do not declare the entire VO-US repository as one homogeneous train split. UTAU banks, human singing, choral recordings, parallel-training-only material, speech-only material, and evaluation sets must remain separately addressable and must not be silently mixed.

### Migration and implementation order

1. [ ] Run an authenticated, read-only tree and metadata inspection first (for example, `hf datasets ls SEKOIA2900/VO-US --tree` and `hf repos ls --filter dataset --limit 0`). Save the current tree, revision SHA, visibility, and storage size as a baseline.
2. [ ] Map existing paths to the proposed logical groups without moving or renaming current files.
3. [ ] Add `manifests/datasets.yaml` and `manifests/permissions.yaml` first, with every candidate defaulting to `review_required`.
4. [ ] Add source/license snapshots and attribution only after checking the exact source version. Do not store source audio just to make the catalog complete.
5. [ ] Add only those source files or derived features whose terms explicitly permit the corresponding storage and processing. Enforce the source-specific restrictions already recorded in the free commercial dataset catalog above.
6. [ ] Update the dataset card with explicit configurations or keep it documentation-only if no common loadable dataset schema is ready.
7. [ ] Re-run the existing VO-US voicebank audit and confirm that the added folders do not change voicebank discovery, download selection, or audit output.
8. [ ] Record final repository revision and a diff summary. Do not claim live repository integration until an authenticated upload has been performed and the resulting tree re-fetched.

### Acceptance criteria

- The existing VO-US contents and current UTAU audit behavior remain intact.
- Human singing corpora and UTAU voicebanks are clearly separated and independently selectable.
- Each candidate has a source URL, immutable revision/version, license evidence, attribution, SHA-256, and granular permission statuses.
- Blocked, unclear, share-alike, speech-only, and parallel-training-only sources cannot silently enter the clean commercial training group.
- No source audio is uploaded when terms prohibit raw-audio redistribution or copying to this repository.
- The repository's visibility is explicitly verified before any restricted data is uploaded.
- The Hugging Face Dataset loader does not infer one mixed train split from unrelated corpora.

### Current status

This plan now designates `SEKOIA2900/VO-US` as the intended canonical repository and supersedes the earlier idea of creating a separate `axral-singing-datasets` repository. No Hugging Face files have been changed by this plan update. The live VO-US tree, current visibility, storage usage, and write access still require an authenticated inspection before any repository mutation.


### GUI inspection evidence (2026-11-25)

A read-only screenshot of the Hugging Face **Files** tab was supplied on 2026-11-25 (screen clock 10:21 JST). This is visual evidence only; it does not replace an API/CLI tree snapshot or a local archive audit.

Observed on branch `main`:

- The Files page reports a repository size of approximately **863 MB** and **4 commits**.
- The visible root contains `.gitattributes` (2.5 kB) and three UTAU ZIP archives:
  - `つくよみちゃんUTAU音源.zip` — approximately **479 MB**.
  - `桃音モモSoft.zip` — approximately **107 MB**.
  - `波音リツ連続音Ver1.5.1.zip` — approximately **277 MB**.
- The screenshot displays an abbreviated commit identifier `e0469ff` and a Verified indicator near the latest-upload header. The full revision SHA and exact commit-to-file mapping are not established by the screenshot.
- No `README.md` appears in the visible root listing. The Dataset card tab exists in the UI, but its contents were not opened or verified.
- Xet badges are visible for the large ZIP files.

Implications:

- The currently visible layout is a small, flat root-level archive collection, not yet the proposed structured corpus/manifest layout.
- Preserve all three ZIP paths and their bytes. Do not rename, move, replace, or re-upload them while adding catalog/manifest documentation.
- The displayed sizes sum to about 863 MB, consistent with the repository-size badge (rounding may apply).
- The screenshot does **not** establish the repository's public/private setting, full current commit SHA, archive-internal voicebank roots, license/provenance, or permission to use the audio for hosted processing or ML training.

Updated verification state:

- [x] Capture a screenshot-level baseline of the visible root file inventory and approximate size.
- [ ] Obtain the full immutable revision SHA, full recursive tree, and exact metadata from the Hub API/CLI.
- [ ] Inspect the Dataset card content and Settings visibility/access state.
- [ ] Audit archive contents and discover actual voicebank roots only after a local/hosted processing permission decision has been recorded for each bank.
- [ ] Do not run the hosted GitHub Actions audit merely because the repository is accessible; retain the existing default-deny per-bank permission gate.

The repository has not been modified on Hugging Face. This plan update records the screenshot observation only; it does not assert that the voicebank archives have been downloaded, extracted, licensed for training, or audited.


### Dataset Card / Viewer inspection evidence (2026-11-25)

A second read-only screenshot of the Hugging Face **Dataset card** tab was supplied on 2026-11-25 (screen clock 11:27 JST).

Observed in the UI:

- The page shows **“No dataset card yet”** and offers **“Create Dataset Card”** / **“Add dataset card”**.
- The Dataset Viewer panel says: **“The dataset is currently empty. Upload or create new data files. Then, you will be able to explore them in the Dataset Viewer.”**
- The sidebar reports **75 downloads last month** and **863 MB total file size**.
- This screenshot does not show the Dataset Card contents because no card is present.
- This screenshot does not establish that the repository has no stored files. The earlier Files-tab screenshot visibly listed three UTAU ZIP archives. The Viewer message therefore must be recorded as a Viewer/card state, not as proof that the repository storage is empty.

Implications and next actions:

- [x] Confirm that no Dataset Card is currently displayed.
- [x] Confirm that the Dataset Viewer currently reports no loadable dataset data.
- [ ] Create a descriptive Dataset Card only after documenting the repository's actual purpose, current ZIP inventory, provenance, and known limitations.
- [ ] Keep the initial card documentation-only: do not add a generic dataset loading configuration or declare a mixed training split while the repository contains only separately packaged UTAU voicebanks and no validated common schema.
- [ ] Explicitly explain that the repository currently acts as a voicebank archive/catalog and that the Viewer message does not imply the ZIP files are absent.
- [ ] Record each voicebank's source, exact terms, and permission scope independently. Do not imply that download availability or the 75 monthly downloads authorize hosted processing, ML training, commercial use, or redistribution.
- [ ] Before creating or uploading a README/Dataset Card on Hugging Face, inspect the full repository revision, visibility, and write/access state. No Hugging Face files have been changed by this inspection.

Current evidence remains screenshot-level. Full Hub metadata, recursive tree, and exact current revision SHA are still pending authenticated CLI/API inspection.


### Repository visibility confirmation (2026-11-25)

The repository owner confirmed in chat that `SEKOIA2900/VO-US` is **private**.

- [x] Record owner-confirmed private visibility.
- [ ] Independently verify visibility and exact repository metadata through the authenticated Hub API/CLI before any write operation.
- [ ] Confirm owner write access and storage quota before adding files.
- [ ] Keep source-specific license, hosted-processing, ML-training, commercial-use, model-distribution, and raw-audio redistribution checks separate. Private visibility does not itself grant any of these permissions.

This status is based on the owner's confirmation, not an independently retrieved Hub API response. The earlier screenshots still establish the visible Files/Card UI state only.


### Dataset Card draft prepared (2026-11-25)

- [x] Draft a documentation-only Dataset Card at [`docs/VO-US_DATASET_CARD_DRAFT.md`](docs/VO-US_DATASET_CARD_DRAFT.md).
- [x] Include only screenshot-supported inventory and approximate archive sizes; label the screenshot date and pending full Hub inventory.
- [x] Record that VO-US is owner-confirmed private.
- [x] Leave the repository-wide `license` metadata unset because the three archives may have different source terms and no repository-wide license has been verified.
- [x] State that no common loading schema or train/evaluation splits are declared, and that the Dataset Viewer reported empty on the inspection date.
- [x] Separate engineering/compatibility goals from actual permissions; default all unverified use scopes to review required.
- [x] Create the draft in Axral_vocal_AI and re-fetch it from GitHub to verify the saved content.
- [ ] Review the draft and capture the full VO-US Hub tree, immutable revision, and exact archive metadata.
- [ ] Only after that review, upload the approved card as `README.md` to the private VO-US repository. No Hugging Face write has been performed by this draft step.
