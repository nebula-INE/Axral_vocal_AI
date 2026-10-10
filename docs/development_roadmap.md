# Axral Vocal AI — Development Roadmap

Status: initial sequence; items are not marked complete unless their code and tests have been reviewed.

## Gate 0 — Audit existing VO-SE_vocal

- [x] Locate existing AI manager and document its current behavior.
- [x] Locate the existing UTAU voicebank parser and PrefixMap handling.
- [ ] Inspect pitch curve representation and Desktop/Web boundaries in detail.
- [ ] Record exact reuse points and tests before implementing an adapter.

Audit notes:
- `modules/ai/ai_manager.py` selects model paths and loads a phoneme dictionary, but its current `analyze_async` path emits fixed fallback timing values and `predict_vits_waveform` returns silence. Treat these as scaffolding, not a trained production model.
- `modules/data/oto_parser.py` already handles `oto.ini`, nested files, alias lookup and PrefixMap-related resolution. Axral Vocal AI should consume its normalized output rather than create a competing parser.
- Existing rendering and pitch data must remain untouched during initial contract work.

## Gate 1 — Versioned contracts

- [x] Define initial request/response schema and validation.
- [x] Add unit tests for time, MIDI range, order, finite values and schema versions.
- [x] Add CI for Python 3.10 and 3.12; [ ] confirm the workflow passes.
- [ ] Review the contract against actual VO-SE_vocal note/pitch data types.

## Gate 2 — Voicebank profile adapter

- [x] Define a profile builder around the existing parser's public API.
- [x] Preserve alias-derived inventory hints without claiming canonical phoneme normalization.
- [ ] Cover CV, VCV, CVVC, PrefixMap/multipitch, missing samples and nested oto.ini.
- [x] Keep absolute paths transient for deduplication; returned profiles contain no paths or audio bytes.

## Gate 3 — Dataset and baseline

- [ ] Confirm permitted data sources and provenance.
- [ ] Define target labels and metrics for pitch-expression assistance.
- [ ] Create synthetic fixtures and a deterministic no-learning baseline.
- [ ] Set up a private Kaggle notebook only after data permission checks.
- [ ] Establish voicebank-held-out validation and test splits.

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
