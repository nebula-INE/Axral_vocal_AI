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

## 6. Starter collection register

The following names are **research candidates only**. Listing a voicebank here does not mean its current terms have been checked or that AI training is permitted. Before downloading or using assets, identify the exact voicebank release and record the current primary-source terms.

| Candidate | First intended use | Current status | Required gate before use |
| --- | --- | --- | --- |
| つくよみちゃん (UTAU voicebank; exact release to identify) | First audit candidate | Not yet verified in this repository | Confirm exact release, current terms, local testing permission, AI-training permission, and any model-publication restrictions |
| 桃音モモ (exact voicebank/release to identify) | Alternate layout/alias coverage | Not yet verified in this repository | Confirm release-specific source and terms; do not infer AI-training permission from general fan-use permission |
| 重音テト (UTAU voicebank; exact release to identify) | Compatibility test only unless terms clearly permit more | Not yet verified in this repository | Read current official voice-use rules and FAQ; separately decide testing, training, and distribution |
| デフォ子／唄音ウタ (exact distribution to identify) | Additional baseline candidate | Not yet verified in this repository | Confirm original distribution source, exact version, and applicable terms |

Do not mark a candidate “approved” based on a secondary summary, a search snippet, or the fact that files are publicly downloadable. If terms are ambiguous, leave the status blocked and ask the rights holder or distributor for clarification.

## 7. Local collection sheet template

Keep this register outside the public repository if it contains private correspondence, local paths, or identifying audit details. A sanitized copy may be shared only after review.

| Field | Value to record |
| --- | --- |
| Candidate and exact release | Name, version/release date, source page |
| Primary-source terms | Terms URL, date checked, archived reference if permitted |
| Local compatibility testing | Allowed / denied / unclear; evidence |
| Feature extraction and derived metadata | Allowed / denied / unclear; evidence |
| AI training | Allowed / denied / unclear; evidence |
| Model or output distribution | Allowed / denied / unclear; evidence |
| Audio redistribution | Allowed / denied / unclear; evidence |
| Attribution requirements | Exact required wording and placement |
| Files present | oto.ini, prefix.map, WAV, readme, other config |
| Layout/encoding notes | CV/VCV/CVVC, encoding, nested paths, aliases |
| Audit status | Not started / audited / needs review / blocked |
| Reviewer and date | Person or role, date, notes |

Use separate decisions for local compatibility testing, derived-feature creation, model training, and distribution. Permission for one activity does not imply permission for the others.

## 8. First-run acceptance checklist

For the first permitted candidate:

- [ ] Exact release and primary-source terms recorded before use.
- [ ] Testing/training/distribution decisions recorded separately.
- [ ] Assets remain local; no voicebank WAVs or restricted oto.ini contents are committed.
- [ ] Audit is run with `--redact-root`, and the output is reviewed for identifying aliases/filenames before sharing.
- [ ] Errors, warnings, and unsupported cases are triaged; CLI exit code alone is not accepted as compatibility proof.
- [ ] Alias and prefix resolution are compared with VO-SE_vocal.
- [ ] A small set of expected notes is manually checked using the existing VO-SE_vocal renderer without changing its synthesis/export implementation.
- [ ] The candidate is marked compatible only after a reviewer records the evidence and known differences.

## 9. Kaggle dataset lifecycle (private by default)

Kaggle is a training workspace, not the canonical archive for original voicebanks. Keep the original download and its license evidence in a local, access-controlled source store. Do not upload an asset merely because the Kaggle dataset is private.

### Storage layers

1. **Source vault (local, read-only):** original archive, exact release/version, source URL, terms snapshot/reference, checksum, and permission decision. Never commit this folder to Git.
2. **Audit workspace (local):** parsed `oto.ini`/`prefix.map` inventory, WAV diagnostics, resolver comparison, and a manually reviewed spot-check record. Keep identifying details local unless sharing is allowed.
3. **Approved training package (Kaggle private dataset):** only assets and derived data whose permissions explicitly cover cloud storage and the intended ML use. Use a versioned manifest and opaque IDs. Keep each source's permission evidence in the manifest; exclude `review_required` and `prohibited` sources.
4. **Training outputs:** model checkpoints, logs, metrics, and dataset version identifiers. Check these for embedded samples, aliases, local paths, or other source-identifying data before sharing or publishing.

### Recommended dataset layout

```text
axral-vocal-ai-dataset-v001/
  dataset_manifest.json
  permission_register.csv
  records/
    train.jsonl
    validation.jsonl
    test.jsonl
  features/                 # only when permitted and needed
  checksums.sha256
  README.md
```

Keep raw WAV files in a separate, explicitly approved directory or dataset version only when the training method genuinely requires them and the license permits cloud storage. Do not duplicate all voicebank WAVs by default. For the initial pitch-delta model, prioritize curated note/feature/target records and evaluate whether raw audio is needed at all; never manufacture pitch ground truth from unverified curves.

### Versioning and access

- Create a private Kaggle Dataset for each immutable dataset release (for example, `v001`); create a new version when records or labels change, and record its dataset/version identifier in every training run.
- Keep the dataset private, do not add collaborators unless needed, and do not publish a Notebook or output that exposes restricted inputs.
- Track file checksums, schema version, preprocessing code/version, source IDs, and train/validation/test assignment so each run can be reproduced.
- Verify Kaggle's current quota and storage rules in its official documentation before upload; quotas and interface behavior can change.
- Private visibility limits ordinary access but does not replace the rights holder's permission, the platform's terms, or a review of what the training output may reveal.
- If permission is unclear, keep the source local and use synthetic fixtures or explicitly authorized data instead.

### Before the first upload

- [ ] Exact release and terms recorded; permission explicitly covers cloud upload/storage and intended ML use.
- [ ] Model/output distribution and derived-feature use assessed separately.
- [ ] Only the minimum required files are included; no unrelated voicebanks or personal/local-path data.
- [ ] Manifest, checksums, schema validation, and group-based split manifest are generated.
- [ ] A small dry run completes on synthetic fixtures before the approved dataset is attached to a GPU notebook.
- [ ] Notebook visibility and dataset visibility are checked independently.
