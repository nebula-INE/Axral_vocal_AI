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

At the implementation checkpoint on 2026-11-11, the live Hub download had not been executed and the public Hub tree could not be fetched from that runtime. The post-merge checkpoint below supersedes the session-specific note; it still does not claim a live-data pass.

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


## Post-merge checkpoint (2026-11-14)

### Verified repository state

- [x] PR [#62](https://github.com/nebula-INE/Axral_vocal_AI/pull/62) was merged on 2026-11-13 at 23:31 JST (merge commit `5b30f18210b15fca94d4e5d8aa11fbe781277fe2`).
- [x] PR [#63](https://github.com/nebula-INE/Axral_vocal_AI/pull/63) was merged on 2026-11-13 at 23:31 JST (merge commit `077aa5575fd7e70407ad2fd901251ff3a312caa4`); this was the `main` HEAD when checked.
- [x] The post-merge `main` push workflow [run 43443576697](https://github.com/nebula-INE/Axral_vocal_AI/actions/runs/43443576697) completed successfully. Both Python 3.10 and Python 3.12 jobs passed **740 tests each**.
- [x] The Kaggle notebook `kaggle/Axral_Vocal_AI_OneCell.ipynb` contains one executable code cell. The only editable code setting is `HF_DATA_URL`; hosted-processing acknowledgement and optional Hub authentication are separate Kaggle Secrets.
- [x] Static inspection confirms the Kaggle permission gate executes before cleanup/download, and the final ZIP is built from an explicit allowlist after temporary source data is removed.

### Live data and permission status — not yet verified

- [ ] No live download or audit of `SEKOIA2900/VO-US` has been completed. Actual repository layout, eligible file list, selected size, and discovered voicebank-root count remain unknown.
- [ ] The four starter rows in `docs/voicebank_permission_register.template.csv` remain `not_started`; exact releases are `not_identified`, and every permission scope remains `review_required`.
- [ ] Do not set the GitHub Actions `permission_reviewed=yes` input or Kaggle Secret `AXRAL_HOSTED_PROCESSING_REVIEWED=yes` until the exact releases and terms explicitly allow processing on the respective hosted platform.
- [ ] No real-data training has been run. The current Kaggle trainer is a metadata-only pitch-delta ridge-regression MVP and requires exactly one fully validated, permission-approved labelled JSONL manifest. A voicebank archive or WAV collection alone does not provide supervised pitch-expression labels and is not a singing-synthesis training set.

### Next execution sequence

1. Identify the exact voicebank releases selected from the dataset and register each release's primary source, terms URL, checked date, and independent permission scopes. Record the hosted platform(s) explicitly in the evidence/notes.
2. After hosted processing is approved for every selected bank, run the manual GitHub Actions audit with a narrowly scoped `file_path_filter` where the Hub layout is known; inspect only the sanitized aggregate artifact and record the immutable Hub commit SHA.
3. Separately enable the Kaggle hosted-processing secret only when Kaggle processing is also permitted. Run the one-cell notebook with the dataset URL and optional `HF_TOKEN`; confirm the sanitized report and training-block reason before treating any result as validated.
4. Keep training, model distribution, and audio redistribution as separate approval decisions. Do not change VO-SE_vocal renderer, playback, or export behavior as part of this audit.

CI success verifies the repository's tested code paths; it does not replace the live-data, license, compatibility, or listening checks above.
