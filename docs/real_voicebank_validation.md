# Real UTAU Voicebank Validation Gate

This checklist is the next validation step after synthetic CI fixtures. Passing the unit suite is not evidence that every real voicebank is compatible.

## 1. Permission and privacy gate

- Use only voicebanks whose license/terms permit local testing for this purpose.
- Keep voicebank WAVs, oto.ini contents, and other restricted assets out of Git commits, issue comments, CI artifacts, and public logs unless redistribution is explicitly permitted.
- Record the voicebank name/version and license URL locally. Prefer a local report with paths relative to the voicebank root; review it before sharing because aliases and file names may identify a bank.
- A local audit can be performed without uploading the voicebank. The GitHub Actions and Kaggle routes are hosted processing: selected archives/audio are transferred to the provider's ephemeral runner or workspace. Use those routes only when the exact voicebank terms explicitly permit that hosted processing.

## 2. Run a local audit

From a checkout with the package importable (for example, after `python -m pip install -e .`):

```sh
python -m axral_vocal_ai.voicebank_audit_cli "/path/to/voicebank" --output audit.json
```

For a report that omits the absolute voicebank root and keeps WAV metadata paths relative, use:

```sh
python -m axral_vocal_ai.voicebank_audit_cli "/path/to/voicebank" --output audit.json --redact-root
```

Root redaction is not full anonymization: aliases, relative sample names, and issue details may still identify a voicebank. Review the report before sharing it.

Exit status:
- `0`: no findings at the selected threshold (default: errors only); inspect warnings and informational findings too.
- `1`: one or more findings met `--fail-on` threshold.
- `2`: the root could not be scanned or the report could not be written.

Useful stricter check:

```sh
python -m axral_vocal_ai.voicebank_audit_cli "/path/to/voicebank" --output audit.json --fail-on warning
```

The report is an inventory and diagnostic aid, not a pass/fail guarantee for rendering or pronunciation. PCM signal checks flag obvious digital silence, near-silence, and suspected clipping; they do not judge phonetic quality or musical suitability.

## 3. Minimum bank matrix

Evaluate several legally usable banks with materially different layouts, rather than several near-identical banks:

- CV and VCV; include CVVC or other formats when available.
- Japanese names/aliases encoded as UTF-8, UTF-8 with BOM, and CP932 where represented by the selected banks.
- Root and nested `oto.ini`, nested sample folders, and Windows-style relative separators.
- `prefix.map` with legacy two-column and three-column rows, multiple pitch boundaries, and notes below/at/above boundaries.
- Duplicate aliases, missing samples, malformed rows, and WAVs with unsupported or damaged headers.
- A bank with intentionally unusual alias spelling, including leading symbols, spaces, and suffix/prefix conventions.

Do not invent a format expectation just because a row looks unusual: record the bank's documented convention and compare behavior with the target VO-SE_vocal resolver.

## 4. Compare against VO-SE_vocal

For each bank, record:

1. Which `oto.ini` files and entries were discovered.
2. Whether every referenced sample resolves to the same file in Axral and VO-SE_vocal.
3. Duplicate alias groups and whether both systems preserve ambiguity or select a candidate.
4. The effective `prefix.map` selection for representative MIDI notes below, on, and above each boundary.
5. Any differences in malformed-row handling, path casing, encodings, and nested maps.
6. A small, manually checked set of notes rendered by VO-SE_vocal, including expected alias, selected sample, and audible result.

Treat nested `prefix.map` files reported by Axral as audit inventory until runtime behavior has been confirmed. Do not assume that combining all discovered maps matches VO-SE_vocal's loading behavior.

## 5. Record results

Keep one row per bank in a local review sheet:

| Field | Record |
| --- | --- |
| Bank/version and license | Name, version, permission reference |
| Environment | OS, Python version, VO-SE_vocal commit |
| Audit summary | oto files/entries, WAVs checked/invalid, errors/warnings |
| Alias comparison | matched, mismatched, ambiguous, unresolved counts |
| Prefix comparison | tested MIDI notes and any differences |
| Render spot-check | test project/reference notes and observed outcome |
| Decision | pass, pass with known differences, blocked; reviewer and date |

A bank should not be marked compatible merely because the CLI exits 0. Compatibility requires the resolver comparison and render spot-check. Only after this gate should the pipeline be used to produce training labels for that bank; hold out at least one distinct bank for evaluation.

## Scope boundaries

- This is a filesystem, metadata, and signal audit. It does not prove pronunciation correctness, phoneme segmentation, oto timing quality, or rendering equivalence.
- The CLI does not modify voicebanks and does not render audio.
- Keep VO-SE_vocal/WORLD rendering behavior as the source of truth. Any renderer change requires a separate reviewed task.


## 6. GitHub Actions audit from Hugging Face

The repository workflow `.github/workflows/hf-utau-voicebank-audit.yml` audits the Hugging Face dataset `SEKOIA2900/VO-US` without placing source voicebank data in Git.

Run it manually from **Actions → Hugging Face UTAU Voicebank Audit → Run workflow**. The workflow is intentionally manual-only; its weekly schedule is disabled until the selected voicebanks' hosted-processing permissions have been reviewed and recorded. It resolves the requested Hub revision to a commit SHA and records that SHA in its report.

Before the first checkout or Hugging Face request, the workflow requires permission_reviewed=yes. The default is no, which stops the job before it checks out code or downloads data. Set it to yes only after you have checked the exact release-specific terms for every voicebank that the file filters can select and confirmed that processing on GitHub Actions is allowed. This is an operator acknowledgement, not an automatic license verifier or a grant of permission.

Manual inputs:
- permission_reviewed: required choice no or yes; defaults to no. The job exits before checkout/download unless set to yes after the review described above.
- `revision`: Hub branch, tag, or commit SHA; default `main`. Invalid dataset IDs/revisions (including control characters, path traversal components, and Markdown-injection text) are rejected before Hub API access. The resolved Hub revision must be a full 40-character commit SHA before file listing and download.
- `file_path_filter`: optional case-insensitive substring matched against Hugging Face file paths before download, reducing the selected bytes. Use a path fragment present in the Hub repository (for example a bank folder or archive name).
- `voicebank_filter`: optional case-insensitive substring matched against discovered bank directories after extraction. This narrows audited roots but does not reduce the download selection.
- `max_download_mb`: pre-download limit for selected archive/metadata/WAV files; default and hard ceiling 4096 MiB. Lower values are allowed; higher values are rejected before Hub API access.
- `max_extracted_mb`: aggregate uncompressed archive limit; default and hard ceiling 8192 MiB. Lower values are allowed; higher values are rejected before Hub API access.
- `fail_on`: `error` (default), `warning`, or `never`.

The downloader selects supported ZIP/UAR and tar archives plus standalone `oto.ini`, `prefix.map`, and WAV files. Its Hugging Face allowlist escapes glob metacharacters in repository paths, preventing names containing `*`, `?`, or `[` from matching unrelated files. It allows at most 512 archives, 100,000 members per archive, and 250,000 members across the complete dataset selection. TAR metadata is streamed without retaining `TarInfo` objects, and ZIP central-directory counts are preflighted from the EOCD before `ZipFile` allocates its in-memory member index. ZIP/tar members that are absolute, escape the extraction root, or represent links/special files are rejected. Archive extraction runs in a temporary directory and its contents are deleted when the job ends.
For ZIP entries without the UTF-8 filename flag, the extractor tries CP932 and restores the member path only when the decoded result contains Japanese-script characters. Path traversal and duplicate-path checks run on that restored name. UTF-8 names and non-Japanese CP437 names remain unchanged; ambiguous names still require manual review. For voicebank discovery, nested pitch-layer `oto.ini` folders are grouped under their outermost enclosing directory containing a regular, non-symlink `prefix.map`. Separate `oto.ini` roots without a shared `prefix.map` remain separate banks. This avoids counting each pitch layer as a different voicebank when the bank has one shared pitch map.

The CLI audit is read-only. The Actions artifact and step summary contain only aggregate counts and issue codes; archive extraction failures are grouped by stable error code (for example, `archive_duplicate_path`) without including archive names or paths. Detailed JSON containing aliases, filenames, and paths is deliberately not uploaded. WAVs, extracted voicebanks, and detailed parser output remain on the ephemeral runner. Per-bank rows include a 16-hex fingerprint derived from each voicebank root's path relative to the selected download/extraction area. This is a stable comparison key for repeated audits of the same repository layout; it is not a voicebank name or a license identifier.

This workflow is a parser/filesystem/signal audit only. It does not infer ML training permission, generate training labels, train a model, or establish rendering compatibility. Confirm each voicebank's own terms before any separate training or redistribution use. The default public Hub request does not require a token; a repository secret named `HF_TOKEN` can be provided for gated access.

## 7. Japanese metadata encoding diagnostics

The audit reports `metadata_replacement_character` when `oto.ini` or `prefix.map` contains U+FFFD, and `metadata_suspected_mojibake` for strong UTF-8/CP932 mojibake signatures. The detector requires a line containing a known mojibake marker to round-trip through CP932 encoding and UTF-8 decoding into different Japanese text. This checks the reversible byte pattern behind common UTF-8-as-CP932 corruption rather than relying on marker counts, so valid Japanese text containing multiple marker characters is not flagged merely for that reason. The original metadata is preserved and never auto-repaired. Both findings are included only as aggregate issue-code counts in the uploaded report. Select `fail_on: warning` when these findings should fail the audit job; the default `error` threshold records warnings without failing the run.

## 8. Starter collection register

The names below are research candidates only. No candidate is marked as licensed for hosted processing, feature extraction, ML training, model distribution, or audio redistribution. The exact release and primary-source terms must be identified before acquisition or processing.

| Candidate | First intended use | Release/permission status | Required gate |
| --- | --- | --- | --- |
| つくよみちゃん UTAU voicebank | First audit candidate | Exact release not yet registered; all scopes review_required | Verify source, exact release, hosted-processing permission, ML-training permission, and output restrictions |
| 桃音モモ | Layout/alias coverage | Exact distribution not yet identified; all scopes review_required | Verify the release-specific terms; fan-use permission does not imply AI-training permission |
| 重音テト | Compatibility testing candidate | Exact UTAU release not yet registered; all scopes review_required | Check official voice-use rules and FAQ separately for testing, training, and distribution |
| デフォ子／唄音ウタ | Additional baseline candidate | Exact distribution not yet identified; all scopes review_required | Verify original distributor, exact version, and all applicable terms |

Use docs/voicebank_permission_register.template.csv as the blank collection sheet. Keep completed registers containing private correspondence, non-public source locations, or personal contact details outside the public repository. Do not mark a voicebank approved based on a search result, a secondary summary, or the fact that it is downloadable from Hugging Face.

## 9. Permission scopes are independent

Record each scope separately for every exact voicebank release:

- local_processing: local inventory, metadata parsing, and compatibility tests.
- hosted_processing: processing on GitHub Actions, Kaggle, or another hosted runner/workspace.
- feature_extraction: creation of derived metadata/features from source files.
- ml_training: use as AI training data.
- model_distribution: publishing, sharing, or selling trained weights/models.
- audio_redistribution: redistribution of original or derived audio samples.

Use only approved, review_required, or prohibited as register values. An approval in one scope never implies approval in another. In particular, local processing permission does not authorize upload to Kaggle or GitHub Actions; ML training permission does not authorize model publication or audio redistribution. Keep the exact terms URL, date checked, reviewer, and evidence reference with the decision. If a term is unclear, keep the scope at review_required.

The Kaggle training manifest mirrors these scopes per record. Labelled training requires feature_extraction and ml_training to be approved, plus the processing location used by the run (local_processing or hosted_processing). The one-cell Kaggle notebook uses the hosted context and requires the Kaggle Secret AXRAL_HOSTED_PROCESSING_REVIEWED=yes before deleting prior temporary data or downloading a dataset. Set that secret only after reviewing every selected bank's terms. Model distribution and audio redistribution remain independent and are not approved by a successful training run.

## 10. Kaggle dataset lifecycle

Kaggle is an optional training workspace, not the canonical archive for original voicebanks.

1. **Source vault (local, read-only):** keep the original archive, exact version, source URL, terms reference, checksum, and permission decisions. Do not commit this folder to Git.
2. **Audit workspace (local by default):** keep detailed oto.ini/prefix.map inventory, WAV diagnostics, resolver comparisons, and listening notes locally. Redact and review before sharing.
3. **Approved training package (private Kaggle dataset):** include only sources whose permissions explicitly cover cloud storage/processing and the intended feature extraction and ML training. Use opaque IDs and a reviewed manifest. Keep review_required and prohibited sources out.
4. **Training outputs:** check checkpoints, reports, logs, and metrics for embedded samples, aliases, record IDs, local paths, or other source-identifying data before sharing.

Private visibility is an access control, not a substitute for the rights holder's permission or the platform's terms. Do not upload raw WAVs by default; include them only when the method needs them and the permission explicitly covers hosted storage and processing. The current pitch-delta MVP consumes approved metadata/labels and does not train on waveform audio. Do not manufacture pitch labels from unverified curves.

## 11. First permitted real-bank run

- [ ] Exact voicebank release and primary-source terms recorded.
- [ ] Local processing and hosted processing decisions recorded separately.
- [ ] Feature extraction and ML training decisions recorded separately.
- [ ] Model distribution and audio redistribution decisions recorded separately.
- [ ] Hosted processing on the chosen provider is explicitly allowed before setting the workflow/Kaggle acknowledgement.
- [ ] Original WAVs and detailed metadata remain out of Git and public artifacts.
- [ ] Run the audit, inspect sanitized counts, then compare alias and prefix resolution with VO-SE_vocal.
- [ ] Manually render a small note set with the existing VO-SE_vocal renderer; do not change its synthesis/export path for this audit.
- [ ] Mark compatibility only after recording resolver and listening evidence, known differences, reviewer, and date.
