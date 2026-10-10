# Axral Vocal AI — Development Roadmap

Status: staged implementation; no production-renderer changes are in scope.

## Gate 0 — Audit existing VO-SE_vocal

- [x] Locate existing AI manager and document its current behavior.
- [x] Locate the existing UTAU voicebank parser and PrefixMap handling.
- [x] Inspect the OtoParser and PrefixMap public API and existing parser tests.
- [x] Record exact reuse points and add a real-parser integration-test path.
- [x] Inspect the Python pitch-event model, graph-editor evaluation, native automation value conversion, and native render-curve boundary.
- [x] Trace the Web PBS/PBW/PBY note-to-WASM pitch path; see `docs/web_pitch_path_audit.md`.
- [ ] Verify Desktop/Web project import/export parity and test the full curve-to-Hz adapter before integration.
- [x] Add Web-side deterministic unit tests for PBS/PBW/PBY parsing, negative PBS offsets, clamping, linear sampling, slew limiting, and tick/ms conversion in `VO-SE_vocal/tests/test_web_pitch_curve.mjs` (committed on `main`; execution/CI result still pending).
- [x] Add a parse → editor serialize → parse regression test in `VO-SE_vocal/tests/test_web_pitch_curve.mjs` and correct the 10× unit mismatch at the Web editor serialization boundary: `serializePitchBend()` now converts semitone offsets to UST tenths, matching `parsePitchBend()`. Commits are on `main`; execution/CI and representative existing-UST compatibility verification are still pending. No renderer/audio-processing code was changed.

Audit findings:
- `modules/ai/ai_manager.py` is scaffolding: its current analysis path emits fixed fallback timing values and `predict_vits_waveform` returns silence. It is not a trained model.
- `modules/data/oto_parser.py` exposes `load_voice_dir()`, `all_aliases()`, `get()`, `has_vcv()`, and `resolve_alias(lyric, prev_vowel=None, note_num=None)`. Axral consumes this public surface rather than implementing a second resolver.
- `modules/data/prefix_map.py` owns PrefixMap parsing and boundary selection. The real-parser fixture confirmed the greatest boundary not above the MIDI note is selected; notes below the first boundary have no mapping.
- Duplicate aliases are first-wins according to sorted `oto.ini` discovery order. Profile sample counts count unique existing files reachable through the parser's public alias table, not every WAV physically present in a bank.
- `modules/data/data_models.py::PitchEvent` stores `time` in seconds and `value` as an untyped float. `ProjectModel.pitch_automation` serializes these points as `time`/`value`; the model itself does not define a musical unit.
- `modules/gui/graph_editor_widget.py` uses a nominal Pitch value range of -8192..8191. Its `get_value_at_time()` is step-hold (last point at or before the requested time), but its graph draws straight lines between points. Thus the visible line is not the same as the sampled evaluation function.
- Native `include/AutomationPoint.h` documents the same numeric range. `include/AutomationCurves.h::evaluate()` also uses step-hold. `pitchValueToSemitones()` maps values using `(value / 8191) * 2.0`, and `src/PluginProcessor.cpp` applies the result as a frequency ratio `2^(semitones/12)`. This is an implementation conversion of the current native automation control, not proof that every stored/project/Web pitch value has been authored in calibrated semitones.
- The negative endpoint is asymmetric: -8192 maps slightly below -2 semitones under the current formula, while +8191 maps to +2. Do not “correct” this in the production code as part of AI work; first define and test compatibility requirements.
- Native render interfaces such as `include/vose_core.h` and `include/vose_streaming_api.h` carry per-sample `pitch_curve` arrays in Hz. This is a different representation from sparse `PitchEvent(time, value)` automation points. They must not be interchanged or labeled with the same unit.
- The Web note editor stores UST-style `PBS/PBW/PBY` strings. `src/utils/pitchCurve.ts` applies a fixed 0.1 scale to heights, producing semitone offsets; the Web render bridge smooths/samples these and passes a dense Hz pitch curve to WASM. This is separate from native Graph Editor automation.
- Web `sampleSemitoneAt()` uses linear interpolation and endpoint hold; `smoothPitchBendPoints()` adds clamping and slew limiting. Native Graph Editor automation evaluation is step-hold. These are not equivalent curve semantics.
- Web pitch-path audit is source-only and did not change VO-SE_vocal. Desktop/Web project serialization parity and deterministic curve-to-Hz tests remain open.
- Real-parser integration tests use a separate checkout via `VO_SE_VOCAL_ROOT`; the AI repository's CI does not modify the production repository.

## Gate 1 — Versioned contracts

- [x] Define initial request/response schema and validation.
- [x] Add unit tests for time, MIDI range, ordering, finite values, and schema versions.
- [x] Add CI for Python 3.10 and 3.12.
- [x] Review the contract against actual VO-SE_vocal note and pitch data types; keep uncalibrated pitch automation excluded from semitone conversion.
- [x] Confirm current-head CI passes for the real-parser integration path.

## Gate 2 — Voicebank profile adapter

- [x] Define a profile builder around the existing parser's public API.
- [x] Preserve alias-derived inventory hints without claiming canonical phoneme normalization.
- [x] Add unit coverage for CV-shaped and VCV-shaped aliases, caller-supplied CVVC/PrefixMap hints, nested/folder-qualified alias shapes, multipitch boundaries, duplicate sample references, and unresolved/missing sample references.
- [x] Keep absolute paths transient for deduplication; returned profiles contain no paths or audio bytes.
- [x] Add integration coverage against the real VO-SE_vocal OtoParser for CV/VCV, PrefixMap pitch-boundary selection, nested `oto.ini`/folder-qualified aliases, and missing WAV candidates.
- [x] Confirm current-head CI passes. CVVC remains a caller-supplied format hint; the audited public parser API has no canonical CVVC detector.

## Gate 3 — Dataset and baseline

- [x] Add a non-mutating pitch-response safety gate with bounded semitone deltas, request correlation, note-interval coverage, and explicit rest exclusion.
- [ ] Confirm permitted data sources and provenance.
- [x] Draft target-label provenance, semitone-unit guardrails, evaluation metrics, and split/leakage policy in `docs/pitch_labeling_and_metrics.md`.
- [x] Add a synthetic fixture and deterministic zero-delta baseline with semitone MAE.
- [x] Execute baseline, profile, and real-parser integration tests in CI on the previously verified PR head.
- [ ] Establish voicebank-held-out validation and test splits for any future approved real dataset.
- [ ] Set up a private Kaggle notebook only after data permission and label-definition checks.

## Gate 4 — Small model experiment

- [ ] Train a small model in Kaggle and record seed, dependencies, GPU, data version, and metrics.
- [ ] Compare with the deterministic baseline and unseen voicebanks.
- [ ] Export a model manifest and verify schema compatibility.
- [ ] Do not integrate until regression and audio-quality gates pass.

## Gate 5 — Opt-in integration

- [ ] Route every model response through `validate_pitch_response()` before any preview/renderer adapter.
- [ ] Review the conservative ±2-semitone default against approved training labels; keep it configurable and never silently clamp proposals.
- [ ] Add AI behind an explicit opt-in flag.
- [ ] Apply results to a preview/copy, never in-place to original note/pitch data.
- [ ] Keep the existing renderer and no-AI path unchanged.
- [ ] Complete Desktop/Web parity tests and repeatable audio regression tests before any integration.

## Out of scope for the first MVP

- Replacing the existing renderer.
- Training a waveform-generating singing synthesizer.
- Automatically uploading user voicebanks or projects to cloud services.
- Committing training audio, datasets, credentials, or checkpoints to this repository.
- Modifying production pitch automation, WORLD synthesis, note timing, volume, noise, or sample placement as part of AI contract work.
