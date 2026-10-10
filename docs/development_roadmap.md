# Axral Vocal AI — Development Roadmap

Status: initial sequence; items are not marked complete unless their code and tests have been reviewed.

## Gate 0 — Audit existing VO-SE_vocal

- [x] Locate existing AI manager and document its current behavior.
- [x] Locate the existing UTAU voicebank parser and PrefixMap handling.
- [x] Inspect the OtoParser and PrefixMap public API and existing parser tests.
- [x] Record exact reuse points and add a real-parser integration-test path.
- [ ] Inspect pitch curve representation and Desktop/Web boundaries in detail.

Audit notes:
- `modules/ai/ai_manager.py` selects model paths and loads a phoneme dictionary, but its current `analyze_async` path emits fixed fallback timing values and `predict_vits_waveform` returns silence. Treat these as scaffolding, not a trained production model.
- `modules/data/oto_parser.py` exposes `load_voice_dir()`, `all_aliases()`, `get()`, `has_vcv()`, and `resolve_alias(lyric, prev_vowel=None, note_num=None)`. Its `resolve_alias` uses `map_alias` / `select_prefix_map` and handles folder-qualified aliases. Axral consumes this public surface instead of implementing a second resolver.
- `modules/data/prefix_map.py` exposes `parse_prefix_map()`, `select_prefix_map()`, and `map_alias()`; boundary selection uses the greatest boundary not above the MIDI note, and notes below the first boundary have no mapping.
- Integration tests now use the actual parser from a separate checkout via `VO_SE_VOCAL_ROOT`; the workflow checks out `nebula-INE/VO-SE_vocal` and runs those tests without modifying the production repository.
- Existing rendering and pitch data must remain untouched during initial contract work.

## Gate 1 — Versioned contracts

- [x] Define initial request/response schema and validation.
- [x] Add unit tests for time, MIDI range, order, finite values and schema versions.
- [x] Add CI for Python 3.10 and 3.12.
- [ ] Confirm a passing workflow run for the current head, including the newest profile tests.
- [ ] Review the contract against actual VO-SE_vocal note/pitch data types.

The last confirmed successful workflow was for commit `2d19ca186557099aed0fbfb55c4af241f01f741e`; subsequent profile changes still need CI confirmation.

## Gate 2 — Voicebank profile adapter

- [x] Define a profile builder around the existing parser's public API.
- [x] Preserve alias-derived inventory hints without claiming canonical phoneme normalization.
- [x] Add profile unit coverage for CV-shaped and VCV-shaped aliases, caller-supplied CVVC/PrefixMap hints, nested/folder-qualified alias shapes, multipitch boundaries, duplicate sample references and unresolved/missing sample references.
- [x] Keep absolute paths transient for deduplication; returned profiles contain no paths or audio bytes.
- [x] Add integration coverage against the real VO-SE_vocal OtoParser for CV/VCV, PrefixMap pitch-boundary selection, nested `oto.ini`/folder-qualified aliases, and missing WAV candidates.
- [ ] Confirm the new integration tests pass on the current PR head in CI. CVVC remains a supplied format hint; the parser API audit has not established a canonical CVVC detector.

## Gate 3 — Dataset and baseline

- [ ] Confirm permitted data sources and provenance.
- [x] Draft target-label provenance, semitone-unit guardrails, evaluation metrics and split/leakage policy in `docs/pitch_labeling_and_metrics.md`.
- [x] Add a synthetic fixture and deterministic zero-delta baseline with semitone MAE.
- [ ] Execute and review the baseline, profile, and real-parser integration tests in CI at the current head. A green result has not yet been confirmed.
- [ ] Establish voicebank-held-out validation and test splits for any future real dataset.
- [ ] Set up a private Kaggle notebook only after data permission checks.

## Gate 4 — Small model experiment

- [ ] Train a small model in Kaggle and record seed, dependencies, GPU, data version and metrics.
- [ ] Compare with the deterministic baseline and unseen voicebanks.
- [ ] Export a model manifest and verify schema compatibility.
- [ ] Do not integrate until regression and audio-quality gates pass.

## Gate 5 — Opt-in integration

- [ ] Add AI behind an explicit opt-in flag.
- [ ] Apply results to a preview/copy, never in-place to original note/pitch data.
- [ ] Keep the existing renderer and no-AI path unchanged.
- [ ] Validate Desktop and Web data flow and run repeatable audio regression tests.

## Out of scope for the first MVP

- Replacing the existing renderer.
- Training a waveform-generating singing synthesizer.
- Automatically uploading user voicebanks or projects to cloud services.
- Committing training audio, datasets, credentials or checkpoints to this repository.
