# Architecture (initial proposal)

Status: Draft. This document records boundaries to guide the initial audit; it is not a claim that these components are implemented.

## Runtime boundary

```text
VO-SE_vocal project / notes
        |
        v
Existing voicebank + alias resolution
        |
        v
Versioned AI input contract
        |
        v
Axral Vocal AI inference interface
        |
        v
Non-destructive expression deltas
        |
        v
Existing editable pitch/expression data
        |
        v
Existing VO-SE_vocal renderer
```

The AI layer should initially predict editable control data, not replace the renderer or synthesize final audio. Existing rendering remains the fallback path.

## Planned responsibilities

- **Voicebank profile:** normalized metadata derived from voicebank files and existing parser results.
- **Phoneme normalization:** map resolved aliases to a canonical representation while retaining the original alias and sample reference.
- **Inference contract:** versioned input/output schemas independent of Desktop/Web UI details.
- **Expression model:** initially pitch delta only, applied non-destructively and controlled by an explicit strength parameter.
- **Training/evaluation:** reproducible data preparation, split by voicebank where feasible, and report results on unseen voicebanks.

These are planned boundaries, not implemented modules. Before creating duplicate parsers or adapters, audit the current VO-SE_vocal code and reuse its tested behavior.

## Integration audit: current VO-SE_vocal interfaces

Audit reference: `nebula-INE/VO-SE_vocal`, default branch snapshot reviewed on 2026-10-19. This is a source-code interface audit, not a claim that a licensed real voicebank has passed end-to-end validation.

| Concern | Existing source/interface | Integration implication |
| --- | --- | --- |
| OTO metadata | `modules/data/oto_parser.py`: `OtoEntry`, `OtoParser.load_voice_dir()`, `resolve_alias()`; entry timing fields are in milliseconds and `wav_path` resolves the sample path | Adapt parsed entries; do not create a second runtime parser or treat milliseconds as seconds |
| Pitch boundary mapping | `modules/data/prefix_map.py`: `PrefixMapEntry`, `parse_prefix_map()`, `select_prefix_map()`, `map_alias()` | Preserve MIDI boundary semantics and prefix/suffix application; below the first declared boundary remains unmapped |
| VCV resolution | `modules/audio/vcv_resolver.py` | Consume the resolved alias/sample result rather than guessing vowel context inside the AI model |
| CVVC planning | `modules/audio/cvvc_resolver.py` describes CVVC as a phoneme-plan layer and explicitly does not replace the existing VCV renderer | CVVC inference/planning must not be treated as proof that renderer timing/slicing supports CVVC |
| Pitch/expression path | `modules/audio/vo_se_engine_patch.py`, `src/voseCoreClient.ts`, `src/voseCoreWorker.ts`, and `src/App.tsx` | AI integration should propose editable controls at a boundary above the established render path; platform adapters must be audited separately |
| Web sample lookup | `server.js` and `src/App.tsx` use voicebank/sample lookup and pitch-aware sample requests | A future adapter must pass the selected MIDI note and report unresolved samples explicitly; do not substitute a guessed sample |
| AI-side metadata audit | `axral_vocal_ai.voicebank_analysis`, `oto_inventory`, `prefix_map`, and `voicebank_alias` | Useful for offline analysis, but not automatically equivalent to VO-SE runtime resolution; compare results before treating them as authoritative |

### Compatibility findings and boundaries

1. VO-SE's runtime OTO parser uses a first-entry-wins policy for duplicate aliases, while Axral's analysis/resolution path intentionally preserves duplicate candidates and can return an ambiguous result. This difference must remain visible in the profile; never silently collapse ambiguity in AI training labels.
2. The AI-side voicebank audit is read-only and diagnostic. A clean audit does not prove pronunciation quality, sample timing correctness, alias equivalence, or successful rendering.
3. Prefix-map selection is pitch-dependent. The integration request must carry the actual MIDI note number for each note, not a single global pitch label.
4. CV, VCV, and CVVC alias conventions vary by bank. Any canonical phoneme representation must retain the original lyric/alias and the resolver result so it can be traced back.
5. Do not send WAV bytes to the model in contract v1. Metadata is sufficient for the first pitch-expression MVP; any future audio feature requires a separately reviewed data/privacy design.
6. The audit does not authorize renderer changes. Existing VO-SE_vocal/WORLD rendering remains the source of truth.

## Versioned inference contract — v1 draft

The following is a language-neutral JSON contract proposal. It is intentionally independent of Desktop/Web UI implementation and does not imply that an inference runtime is already implemented. Unknown schema versions must be rejected explicitly.

### Request: `axral.vocal-expression.request`

```json
{
  "contract": "axral.vocal-expression.request",
  "schema_version": "1.0",
  "request_id": "caller-generated-unique-id",
  "voicebank": {
    "profile_id": "stable-local-profile-id",
    "profile_version": "1",
    "alias_resolution_status": "resolved"
  },
  "notes": [
    {
      "note_id": "stable-project-note-id",
      "midi_note": 60,
      "start_ms": 0.0,
      "duration_ms": 500.0,
      "lyric": "あ",
      "resolved_alias": "あ",
      "phoneme_key": "あ",
      "sample_ref": "opaque-local-reference",
      "voiced": true,
      "baseline_pitch": [
        { "time_ms": 0.0, "hz": 261.6256 },
        { "time_ms": 250.0, "hz": 261.6256 }
      ]
    }
  ],
  "controls": {
    "enabled_features": ["pitch_delta"],
    "strength": 1.0
  }
}
```

Request rules:

- `schema_version` is required; v1 accepts only the documented shape.
- `midi_note` is an integer in 0–127. `start_ms`, `duration_ms`, and pitch-point `time_ms` are milliseconds; pitch `hz` is hertz.
- `baseline_pitch` is optional. When present, points are relative to the note onset, ordered by `time_ms`, and must lie within the note duration.
- `resolved_alias` and `sample_ref` come from the existing resolver. The model must not invent or replace them.
- If alias resolution is missing, invalid, or ambiguous, the caller must omit that note from inference or mark the request as requiring review; it must not disguise the condition as resolved.
- `sample_ref` is opaque and local. It must not be an absolute filesystem path or contain audio bytes.
- `strength` is finite and in `[0, 1]`; `0` means no AI contribution.

### Response: `axral.vocal-expression.response`

```json
{
  "contract": "axral.vocal-expression.response",
  "schema_version": "1.0",
  "request_id": "caller-generated-unique-id",
  "status": "ok",
  "model": {
    "model_id": "deterministic-stub-or-model-id",
    "model_version": "1"
  },
  "note_results": [
    {
      "note_id": "stable-project-note-id",
      "status": "ok",
      "pitch_delta": [
        { "time_ms": 0.0, "delta_cents": 0.0 },
        { "time_ms": 250.0, "delta_cents": 12.0 }
      ],
      "confidence": 0.8,
      "warnings": []
    }
  ],
  "warnings": []
}
```

Response rules:

- `status` is one of `ok`, `partial`, `needs_review`, or `error`; each note result is independently traceable by `note_id`.
- `delta_cents` is a relative pitch-expression delta, not an absolute pitch and not rendered audio. Times are note-relative milliseconds.
- Results must not include a replacement MIDI note, alias, sample path, waveform, rendered WAV, or mutated project data.
- `confidence`, when present, is finite and in `[0, 1]`. Missing/low-confidence or invalid results require review, not silent coercion.
- The caller validates finite values, time ordering, note-duration bounds, output note IDs, and version compatibility before presenting or applying any result.
- Applying the result creates a separate editable proposal. The original notes and pitch curve remain recoverable; AI-off or any validation failure leaves the established project/render path unchanged.
- The first integration should use a deterministic stub and contract tests before any trained model is connected.

## Safety and compatibility invariants

1. AI disabled means the existing render path is used without AI modifications.
2. AI output must not mutate the user's original note or pitch data in place.
3. Invalid/missing aliases must be reported and handled by the established fallback; do not silently invent a sample.
4. Pitch output must respect unvoiced regions and valid frequency ranges.
5. Model/input schema versions must be checked before inference.
6. Audio regressions must be tested with repeatable fixtures; do not accept changes solely because a model runs.
7. Voicebank audio and training data must not be committed unless rights and repository storage policy are confirmed.
8. This documentation-only integration step must not change rendering, export, WAV writing, synthesis, timing, pitch shifting, or audio processing.

## Proposed development gates

### Gate 0 — Audit
Record existing AI entry points, voicebank/oto.ini parsing, PrefixMap handling, phoneme aliases, pitch curve storage, and Desktop/Web runtime boundaries.

### Gate 1 — Contracts
Define typed, versioned request/response objects and tests without changing synthesis behavior.

### Gate 2 — Voicebank profile
Build profiles by adapting existing parser output; test CV, VCV, CVVC, prefix/suffix, missing aliases, and nested oto.ini layouts.

### Gate 3 — Pitch MVP
Use a stub/deterministic model first to validate data flow and editing. Add a trained model only after data provenance and evaluation criteria are defined.

### Gate 4 — Model evaluation
Evaluate on voicebanks excluded from training, check pitch continuity and musical constraints, compare baseline versus AI-enabled output, and measure memory/runtime.

## Open decisions

- Canonical phoneme inventory and language coverage.
- Model architecture and training corpus.
- Runtime format and backend per platform (e.g. ONNX Runtime, WebGPU, or server inference).
- Model distribution/versioning and large-artifact storage.
- Licensing and consent rules for voicebank data.
