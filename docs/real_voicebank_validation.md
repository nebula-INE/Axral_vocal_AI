# Real UTAU Voicebank Validation Gate

This checklist is the next validation step after synthetic CI fixtures. Passing the unit suite is not evidence that every real voicebank is compatible.

## 1. Permission and privacy gate

- Use only voicebanks whose license/terms permit local testing for this purpose.
- Keep voicebank WAVs, oto.ini contents, and other restricted assets out of Git commits, issue comments, CI artifacts, and public logs unless redistribution is explicitly permitted.
- Record the voicebank name/version and license URL locally. Prefer a local report with paths relative to the voicebank root; review it before sharing because aliases and file names may identify a bank.
- Do not upload a voicebank to an external service as part of this workflow.

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

Run it manually from **Actions → Hugging Face UTAU Voicebank Audit → Run workflow**, or allow its weekly schedule after the workflow has been merged to the default branch. The workflow resolves the requested Hub revision to a commit SHA and records that SHA in its report.

Manual inputs:
- `revision`: Hub branch, tag, or commit SHA; default `main`. Invalid dataset IDs/revisions (including control characters, path traversal components, and Markdown-injection text) are rejected before Hub API access. The resolved Hub revision must be a full 40-character commit SHA before file listing and download.
- `file_path_filter`: optional case-insensitive substring matched against Hugging Face file paths before download, reducing the selected bytes. Use a path fragment present in the Hub repository (for example a bank folder or archive name).
- `voicebank_filter`: optional case-insensitive substring matched against discovered bank directories after extraction. This narrows audited roots but does not reduce the download selection.
- `max_download_mb`: pre-download limit for selected archive/metadata/WAV files; default and hard ceiling 4096 MiB. Lower values are allowed; higher values are rejected before Hub API access.
- `max_extracted_mb`: aggregate uncompressed archive limit; default and hard ceiling 8192 MiB. Lower values are allowed; higher values are rejected before Hub API access.
- `fail_on`: `error` (default), `warning`, or `never`.

The downloader selects supported ZIP/UAR and tar archives plus standalone `oto.ini`, `prefix.map`, and WAV files. ZIP/tar members that are absolute, escape the extraction root, or represent links/special files are rejected. Archive extraction runs in a temporary directory and its contents are deleted when the job ends.
For ZIP entries without the UTF-8 filename flag, the extractor tries CP932 and restores the member path only when the decoded result contains Japanese-script characters. Path traversal and duplicate-path checks run on that restored name. UTF-8 names and non-Japanese CP437 names remain unchanged; ambiguous names still require manual review.

The CLI audit is read-only. The Actions artifact and step summary contain only aggregate counts and issue codes; archive extraction failures are grouped by stable error code (for example, `archive_duplicate_path`) without including archive names or paths. Detailed JSON containing aliases, filenames, and paths is deliberately not uploaded. WAVs, extracted voicebanks, and detailed parser output remain on the ephemeral runner.

This workflow is a parser/filesystem/signal audit only. It does not infer ML training permission, generate training labels, train a model, or establish rendering compatibility. Confirm each voicebank's own terms before any separate training or redistribution use. The default public Hub request does not require a token; a repository secret named `HF_TOKEN` can be provided for gated access.
