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
- Add a separate workflow with `workflow_dispatch` and a weekly `schedule`; do not download third-party voicebank data for arbitrary pull requests.
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
- A scheduled run is bounded by the configured download and execution limits.
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
4. Add the separate GitHub Actions manual/weekly workflow.
5. Run the complete existing test suite and inspect CI results.
6. Update this plan with implementation status and open limitations before opening the pull request.
