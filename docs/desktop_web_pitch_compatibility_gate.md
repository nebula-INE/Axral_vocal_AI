# Desktop/Web Pitch Representation Compatibility Gate

Status: audit specification; no conversion is enabled by this document.

## Purpose

Keep Axral Vocal AI's proposal contract independent of VO-SE_vocal's current editor and renderer internals. A pitch proposal is expressed as sparse, absolute-time offsets in semitones. It must not be interpreted as an existing Desktop automation value or a Web UST field without an explicit adapter.

## Representation inventory

| Boundary | Representation | Time/unit semantics | Evaluation behavior | Integration status |
|---|---|---|---|---|
| Axral request notes | MIDI note number plus start/end | seconds; MIDI 0–127 | note intervals | Contracted and tested |
| Axral AI proposal | sparse `PitchDeltaPoint` | seconds + delta semitones | no interpolation defined by contract | Validation only |
| Python `PitchEvent` / project automation | `time` + untyped numeric `value` | time in seconds; value unit is not encoded | model does not define a unit | Do not map to semitones by assumption |
| Desktop Graph Editor | nominal Pitch values -8192..8191 | native automation numeric domain | evaluator is step-hold; graph drawing is linear | Compatibility policy required |
| Native processor conversion | automation value → semitone offset | current formula: `(value / 8191) * 2.0` | then frequency ratio `2^(semitones/12)` | Preserve existing behavior pending parity spec |
| Native render API | dense pitch array in Hz | one frequency value per sample/frame as defined by API | already sampled | Not interchangeable with sparse automation |
| Web note editor | UST `PBS/PBW/PBY` | PBS heights scaled by 0.1 to semitones; PBW timing converted to ms/ticks | linear semitone sampling, endpoint hold, then smoothing/slew limiting | Web-only path |
| Web WASM bridge | dense pitch curve in Hz | generated from note base frequency and sampled semitone offset | renderer input | Existing path must remain untouched during audit |

## Non-negotiable invariants

1. Never infer units from a field name such as `value` or `pitch`; units must be declared at the adapter boundary.
2. Never pass sparse automation points where a dense Hz curve is expected, or vice versa.
3. Do not assume Desktop step-hold semantics equal Web linear sampling/smoothing semantics.
4. Preserve the native endpoint behavior, including its current negative/positive endpoint asymmetry, until an explicit compatibility decision and regression suite authorize a change.
5. An AI delta is an offset from the note's MIDI-derived base pitch, not an absolute MIDI note number, Hz value, UST PBS height, or native automation integer.
6. Reject invalid or ambiguous conversion inputs. Do not silently clamp, rescale, reorder, or repair source data.
7. Build any preview on a copy. Keep AI disabled by default and preserve the established non-AI renderer path.
8. No changes to WORLD synthesis, production rendering, sample placement, volume, noise, or pitch application are part of this gate.

## Required tests before an adapter can be enabled

- Unit round-trip tests for each supported serialized project representation, using fixtures from both Desktop and Web.
- Explicit unit tests for seconds ↔ milliseconds/ticks, MIDI note ↔ Hz, semitone delta ↔ frequency ratio, and UST PBS scaling.
- Boundary tests at note starts/ends, shared boundaries, rests, zero-length notes, and points just inside/outside tolerance.
- Golden fixtures for positive and negative bends, including PBS offsets and multiple PBW segments.
- Tests that distinguish step-hold from linear interpolation and document any intentional difference.
- Deterministic curve-to-Hz tests against the current Web bridge without changing the production helper.
- A no-AI regression proving source notes/curves and renderer inputs are unchanged when AI is disabled or rejected.
- Desktop/Web import-export parity checks and audio regression tests before any live integration.

## Contract-boundary characterization added

`tests/test_pitch_representation_compatibility.py` now records a small, deterministic set of contract-level cases:

- request parsing preserves seconds, MIDI note numbers, request correlation, and explicit rest metadata;
- negative, zero, and positive semitone offsets remain signed offsets, with isolated frequency-ratio reference checks;
- a proposal at a shared voiced-note/rest boundary is rejected;
- sparse points remain sparse, and the contract does not prescribe step-hold, linear interpolation, or smoothing.

These are guardrail tests for Axral's API contract only. They do not import or execute VO-SE_vocal's Desktop/Web implementation, and they are not evidence of cross-platform parity.

## Current decision

The safe contract remains `PitchDeltaPoint(time_sec, delta_semitones)`. The current PR validates proposal bounds, request correlation, note coverage, and explicit rest exclusion only. It does not convert or apply proposals to either Desktop or Web. Full import/export parity and the renderer-facing curve adapter remain blocked until the required fixtures and tests exist.


## Source-level audit update — 2026-10-11

The current `VO-SE_vocal/main` source was re-read for this audit. This section records observations only; it does not change that repository.

- `modules/data/data_models.py::PitchEvent` explicitly documents `time` in seconds, while `value` is only typed as `float`; no musical unit is encoded in the serialized `time/value` pair.
- `modules/gui/graph_editor_widget.py::get_value_at_time()` returns the most recent point at or before the query time (step-hold). This is observably different from the Web helper's linear interpolation between UST-derived points.
- `src/utils/pitchCurve.ts::parsePitchBend()` uses a fixed 0.1 scale for PBS/PBY heights and represents point times as milliseconds relative to the note. `serializePitchBend()` multiplies semitone values by 10 at the UST serialization boundary. The Web regression test covers this parse → serialize → parse round trip.
- `src/voseCoreClient.ts::buildPitchCurveHz()` converts a MIDI note base frequency plus sampled semitone offset into a dense Hz array. It applies the existing Web smoothing helper before sampling. The bridge and production renderer remain out of scope for changes.
- The bridge declares a 5 ms frame period constant, while the currently inspected helper computes sample times as `i / (frameCount - 1) * durationMs`. Before designing an adapter, characterize how callers derive `frameCount` and `durationMs`; do not assume the comment alone proves every generated sample is exactly 5 ms apart.
- The existing Web tests exercise the actual TypeScript utility and instrument the private bridge helper in memory. They do not establish Desktop/Web equivalence, and they do not prove the whole renderer's audio output is unchanged.

### Verified CI snapshot

The latest PR-head workflow run observed during this audit is [run 38108115190](https://github.com/nebula-INE/Axral_vocal_AI/actions/runs/38108115190), for commit `db6503247ccd9c4d6e9d22777cd21d5e05d2401b`. Both Python 3.10 and 3.12 jobs completed successfully. This validates the Axral repository's current tests only; it is not a VO-SE_vocal build or audio-regression result.

### Next compatibility work

1. Inspect the Desktop project's save/load path and identify the exact serialized key/path used for `pitch_automation`.
2. Inspect all call sites that produce `frameCount` and `durationMs` for `buildPitchCurveHz()`; establish whether the dense Hz array's time grid is 5 ms, endpoint-inclusive, or caller-defined.
3. Add isolated golden fixtures for each representation before any conversion is implemented. Keep the Web production utility and the Desktop evaluator unchanged.
4. Do not claim parity until the same fixtures can be loaded through both real implementations and compared with explicit, agreed interpolation semantics.


## Source-level audit update — save/load and frame-grid trace (2026-10-11)

A second read-only trace of `VO-SE_vocal/main` confirmed the following:

- The legacy `ProjectModel.serialize()` in `modules/data/data_models.py` emits a top-level `pitch_automation` array containing `PitchEvent.to_dict()` objects (`time`, `value`). However, the current GUI JSON load path in `modules/gui/mixins/project_io_mixin.py::load_json_project()` restores Graph Editor automation from top-level `parameters`, with arrays named `Pitch`, `Gender`, `Tension`, and `Breath`. It calls `PitchEvent.from_dict()` for entries that contain both `time` and `value`. These are distinct serialized shapes; do not assume the legacy `pitch_automation` field is the active GUI project's canonical save/load path.
- The current multitrack JSON loader reconstructs track notes from `tracks[*].notes`, then separately restores Graph Editor automation from `parameters`. This confirms the adapter must target the actual `parameters.Pitch` shape if integrating with current Graph Editor state, while retaining explicit compatibility handling for any legacy `pitch_automation` documents.
- The Web bridge call site is in `src/voseCoreClient.ts::pushEvent()`: `p = max(2, round(max(1, durationMs) / 5) + 1)`, and then `buildPitchCurveHz(note, p, durationMs)`. The helper samples at `i / (frameCount - 1) * durationMs`, including both endpoints. Therefore actual spacing is `durationMs / (p - 1)`; because `p` is rounded, spacing is generally near 5 ms rather than guaranteed to be exactly 5 ms. This is a source-level result, not a request to alter the production curve.
- For a gap/rest event, `pushEvent(null, null, ...)` uses `silentFrames(p)`; it does not invoke the pitch-bend helper. The pitch-grid conclusion applies to voiced notes that have a resolved sample.

The current GUI writer was also confirmed in `modules/gui/mixins/project_io_mixin.py::on_save_project_clicked()`: it emits `parameters` with four named arrays (`Pitch`, `Gender`, `Tension`, `Breath`), each serialized as `{time, value}`, plus `tracks[*].notes`. It does not emit the legacy `ProjectModel.serialize()` top-level `pitch_automation` field. The paired loader restores those `parameters` arrays into Graph Editor state. These findings identify serialization and sampling boundaries only. No VO-SE_vocal source or production audio behavior was changed.
