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
