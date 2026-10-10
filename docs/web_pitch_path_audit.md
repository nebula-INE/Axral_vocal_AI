# VO-SE_vocal Web pitch-path audit

Audit date: 2026-10-10
Scope: read-only source audit of the Web pitch-expression path. No files in VO-SE_vocal were changed.

## Executive result

The Web app's editable note pitch bend is **not** the same representation as Python's sparse `PitchEvent(time, value)` automation.

The Web UI stores UST-style `PBS/PBW/PBY` strings on each note. The Web conversion utility interprets the PBY heights using a fixed factor of 0.1, yielding semitone offsets; the Web renderer then smooths these points and samples/interpolates them into a dense pitch trajectory. The WASM core interface receives the dense pitch curve in Hz.

This confirms a specific Web path, but does **not** establish Desktop/Web semantic parity. In particular, the Python/C++ Graph Editor automation path uses a separate sparse-point model and a native value-to-semitone conversion. These paths must not be merged conceptually without a deliberate adapter and compatibility tests.

## Web path traced

1. **Editable project representation**
   - `src/App.tsx` defines Web notes with `pbs`, `pbw`, and `pby` string fields.
   - The UI editor in `src/components/PitchCurveOverlay.tsx` parses these fields for display and editing; edits are serialized back to PBS/PBW/PBY strings.
   - The time axis is note-relative milliseconds in the pitch utility and is converted to/from timeline ticks using the project tempo (480 ticks per beat).

2. **PBS/PBW/PBY parsing**
   - `src/utils/pitchCurve.ts::parsePitchBend()` returns points shaped as `{ offsetMs, semitone }`.
   - It uses a fixed `scaleFactor = 0.1` for the PBS start height and PBY heights. The source comments describe this as the UST/UTAU convention.
   - Parsed semitone values are clamped to ±24 semitones and rounded to two decimal places.
   - PBW segment widths are interpreted as milliseconds and clamped to a 1–5000 ms range; the starting offset is clamped to -3000–10000 ms.
   - This parser's fixed scale is materially different from the Python/C++ Graph Editor automation's nominal -8192..8191 control range mapped to about ±2 semitones.

3. **Web render bridge**
   - `src/voseCoreClient.ts` parses PBS/PBW/PBY, applies `smoothPitchBendPoints()`, and evaluates the pitch bend as a semitone offset over note-relative time.
   - That offset is applied to the MIDI-derived base frequency to construct the render pitch trajectory. The WASM bridge ultimately passes a dense `pitch_curve` array to the native core; the native interface documents this array in Hz.
   - `src/voseCoreWorker.ts` packs the render note and pitch-curve buffers into the WASM ABI. This is a dense-curve/ABI boundary, not a direct serialization of `PitchEvent(time, value)`.
   - `src/wasmEngine.ts` also contains a separate offline JS/Web Audio path that uses the same PBS/PBW/PBY parser and smooth points to schedule a pitch bend. Its presence alone does not prove that it is used when the WASM core succeeds; the app comments state the core is the primary route and fallback is not automatic.

4. **Interpolation and smoothing**
   - `src/utils/pitchCurve.ts::sampleSemitoneAt()` uses linear interpolation between adjacent points and holds the endpoint values outside the point range.
   - `smoothPitchBendPoints()` applies a soft limit and a time-dependent slew limit. This is a Web-specific transformation of the UST bend points before rendering.
   - The Web pitch overlay draws straight line segments between points. That matches the utility's linear sampling model more closely than the Python/C++ sparse automation step-hold evaluation, but the renderer also applies smoothing and conversion to Hz.

5. **Desktop/native Graph Editor path (comparison only)**
   - Python `PitchEvent` has `time` in seconds and an untyped floating-point `value`.
   - Python `GraphEditorWidget.get_value_at_time()` and native `AutomationCurves::evaluate()` use step-hold evaluation, while the GUI draws straight lines.
   - Native `AutomationRanges::pitchValueToSemitones()` uses `(value / 8191) * 2.0`; the negative endpoint -8192 is asymmetric.
   - `src/PluginProcessor.cpp` applies that native automation to the note's existing Hz pitch curve as a frequency ratio. This native graph-automation path is separate from the Web PBS/PBW/PBY path.
   - UST portamento/PBS/PBW/PBY may also enter native processing through the UST/portamento-specific path; that should not be conflated with Graph Editor `PitchEvent` automation.

## Safe conclusions

- Web PBS/PBW/PBY is a note-relative UST-style representation whose heights are converted to semitone offsets using a fixed 0.1 factor in the Web utility.
- The Web render bridge converts the bend to a dense frequency-in-Hz curve before crossing the WASM/native boundary.
- Python/C++ Graph Editor automation is a separate representation with different value range, evaluation behavior, and conversion rules.
- Therefore, there is no single safe formula that can convert every existing `PitchEvent.value`, Web PBS/PBW/PBY value, and dense `pitch_curve` sample into one another without identifying the source path and its semantics.

## Remaining verification before integration

- Add focused tests for the Web pitch parser/sampler and the actual WASM input curve using deterministic fixtures, without changing production audio code.
- Trace project import/export and Web request/render payloads for any route that maps Python project data to Web note data; the current audit establishes the Web note-to-WASM path, not universal Desktop/Web project serialization parity.
- Verify timing origin and tempo conversion across note tick, note-relative milliseconds, and dense curve sample indices, including negative PBS offsets and note boundaries.
- Compare a fixed set of expected curve points/Hz values through the Web adapter in tests. Do not run an unreviewed production-audio rewrite as part of this audit.
- Keep AI outputs as semitone deltas relative to an explicit reference trajectory. Convert to a renderer representation only through a versioned, tested adapter.
- Do not modify the production renderer, WORLD synthesis, pitch/noise/volume processing, sample placement, or output audio for this AI task.

## Training gate

Kaggle training remains blocked until source-data permissions, label provenance, the fixed time grid, voiced/unvoiced rules, and voicebank-held-out splits are approved. This audit used source code only and did not access or upload voicebank audio.
