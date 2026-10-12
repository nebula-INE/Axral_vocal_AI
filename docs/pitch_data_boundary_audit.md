# Pitch data-boundary audit: AI label integration gate

Status: **partially traced; conversion into training labels remains blocked**.

This audit records what the current source code establishes and, equally importantly, what it does not establish. It is not authorization to use a voicebank or to change VO-SE_vocal's rendering behavior.

## Findings verified in source

### 1. Python project model: sparse automation points

File: `modules/data/data_models.py` in `nebula-INE/VO-SE_vocal`

- `PitchEvent` stores `time: float` (seconds) and `value: float`.
- The data model does not declare the unit or semantic meaning of `value`; therefore the object alone cannot be treated as semitone pitch labels.
- Project serialization stores these events as `pitch_automation` objects with `time` and `value`.

### 2. Desktop graph editor: editing range and sampling semantics

File: `modules/gui/graph_editor_widget.py`

- Pitch edit values are bounded by `PITCH_MIN = -8192` and `PITCH_MAX = 8191`.
- `get_value_at_time()` uses step-hold semantics (last point at or before the query time).
- The graph's visual line interpolation is not evidence that the render path uses linear interpolation.
- The editor maps time to pixels through tempo and beat scale, while the stored event time is in seconds.

### 3. Native render-side automation conversion

Files: `include/AutomationCurves.h`, `src/PluginProcessor.cpp`

- `AutomationRanges::pitchValueToSemitones(value)` computes `(value / 8191) * 2.0`.
- The native processor converts that offset to a frequency ratio with `pow(2.0, semitoneOffset / 12.0)`.
- The endpoints are asymmetric: `+8191 -> +2` semitones, while `-8192` is slightly below `-2`.
- This is a current native automation conversion, not proof that all import, Web, or AI-facing values have the same unit.

### 4. Native render bridge: a separate dense representation

Files: `include/vose_core.h`, `include/vose_streaming_api.h`, `include/RenderEngine.h`

- Render bridge `pitch_curve` data is a dense array in Hz, not the sparse `PitchEvent.value` representation and not a semitone-delta label.
- A Hz trajectory must not be fed to the pitch-delta label builder as though it were semitones.

## Unresolved boundary: Web serialization and handoff

The inspected evidence above does **not** establish a complete, tested mapping from Web editor values through serialization/request payloads into the render bridge. The Web source entry point was not verified as part of this audit. Until the exact source files and the full conversion path are identified, do not infer compatibility from a shared field name such as `pitch`, `value`, or `pitch_curve`.

## Required next steps before label integration

1. Locate the actual Web editor model and serialization path; record the exact units and whether timestamps are seconds, milliseconds, ticks, or frame indices at each boundary.
2. Trace the Web render request all the way to the production bridge and identify where (if anywhere) sparse automation becomes a dense Hz curve.
3. Add paired Desktop/Web fixtures for zero, positive and negative offsets, endpoints, sparse points, and gaps. Assert the serialized values and resulting sampled curves—not just UI appearance.
4. Keep the current production formulas unchanged during this audit. If a behavior mismatch is found, isolate it in a separate compatibility issue with regression tests and an explicit product decision.
5. Only after the contract is tested, add an explicit, versioned adapter from the selected source representation to semitone tracks. Then feed those tracks to `build_pitch_delta_labels`; never reinterpret raw `PitchEvent.value` directly.
6. Keep data provenance, rights review, voiced masks, and human approval as independent gates. Passing these engineering checks does not approve any dataset for ML use.

## Acceptance criteria

- [ ] Every field has a documented unit and semantic meaning at each boundary.
- [ ] Desktop and Web time-grid and pitch behavior are compared with deterministic fixtures.
- [ ] Conversion is explicit and versioned; unsupported inputs fail closed.
- [ ] No production rendering behavior changes without separate approval and regression coverage.
- [ ] No real audio, private voicebank files, credentials, or model checkpoints are added to this repository.

## Scope

This is a documentation/audit checkpoint only. It does not connect the label builder to training, modify `VO-SE_vocal`, or claim that Web compatibility has been established.
