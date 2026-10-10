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

## Safety and compatibility invariants

1. AI disabled means the existing render path is used without AI modifications.
2. AI output must not mutate the user's original note or pitch data in place.
3. Invalid/missing aliases must be reported and handled by the established fallback; do not silently invent a sample.
4. Pitch output must respect unvoiced regions and valid frequency ranges.
5. Model/input schema versions must be checked before inference.
6. Audio regressions must be tested with repeatable fixtures; do not accept changes solely because a model runs.
7. Voicebank audio and training data must not be committed unless rights and repository storage policy are confirmed.

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
