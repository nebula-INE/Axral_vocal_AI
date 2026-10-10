# Axral Vocal AI — Data Contracts

Status: initial contract proposal for the non-destructive pitch-expression MVP.

## Goals

- Keep the AI interface independent of Desktop, Web, and tablet UI details.
- Preserve the exact source lyric/alias and resolved voicebank reference for diagnostics.
- Treat pitch assistance as a proposal, never as an in-place edit.
- Reject incompatible schema versions and malformed numeric data before inference.
- Do not make the AI responsible for resolving WAV files or replacing the renderer.

## Request: `PitchRequest`

Schema version: `1`.

Required information:
- `notes`: ordered note records with start/end time in seconds, MIDI note number, original lyric, resolved alias (if any), and voiced/unvoiced status where known.
- `voicebank`: optional descriptive profile (stable identifier if available, format hints, and normalized phoneme inventory). It must not contain raw audio or absolute local paths.
- `context`: optional tempo and time-signature metadata.
- `request_id`: optional caller-generated correlation ID.

Validation:
- Times must be finite; end time must be greater than or equal to start time.
- MIDI note numbers must be finite and in the supported MIDI range 0–127.
- Preserve note ordering; do not silently reorder malformed input.
- Empty or unresolved aliases are allowed in the request, but must remain explicitly unresolved.
- No WAV contents, credentials, or machine-specific absolute paths belong in the serialized request.

## Response: `PitchResponse`

Schema version: `1`.

- `request_id`: copied from the request when supplied.
- `status`: `ok`, `no_change`, or `rejected`.
- `pitch_deltas`: optional ordered pitch-delta points. Each point contains time in seconds and a delta in semitones.
- `warnings`: machine-readable diagnostic strings.

Validation and application:
- The number and timing of returned points must be checked against the request and model's declared output policy.
- Times and deltas must be finite.
- The first MVP must not overwrite the original pitch curve. The caller applies the delta to a separate preview/copy only.
- A response must be rejected if its schema version is unsupported or if any point is invalid.
- Do not apply AI pitch deltas to known unvoiced regions.
- Clamp or reject out-of-range results according to an explicit caller policy; never silently change the original note data.

## Voicebank profile

The profile is derived from the existing VO-SE_vocal parser rather than introducing a second `oto.ini` / `prefix.map` implementation. It may contain:
- counts of aliases and samples,
- supported alias/phoneme patterns,
- pitch-bank boundaries when parsed,
- unresolved/missing-file diagnostics,
- parser/version metadata.

It must not copy audio or leak absolute paths into training records. Keep original alias strings alongside normalized phoneme labels so normalization remains auditable.

## Training record boundary

Training examples should have an explicit provenance record and a documented license/permission status. Split evaluation by voicebank where feasible, not only by randomly splitting adjacent frames from the same voicebank. Do not put voicebank audio, private datasets, checkpoints, or access tokens in this Git repository.

## Compatibility

The initial contract is a proposal. Changes require a schema-version decision and tests. The AI layer must be optional; if it is disabled, VO-SE_vocal continues using its existing pitch and render path unchanged.


## Response validation boundary

`src/axral_vocal_ai/response_validation.py` provides a renderer-independent safety gate for returned proposals:

- verifies request correlation when both request and response carry an ID;
- rejects deltas beyond a caller-configurable absolute semitone bound (default ±2 semitones for the conservative MVP);
- rejects points outside note intervals or inside notes explicitly marked unvoiced/rest;
- permits unresolved notes when voiced status is unknown, rather than treating missing alias resolution as proof of silence;
- returns valid responses unchanged and rejects invalid responses instead of silently clamping them.

This is validation only: it does not apply deltas, interpolate curves, alter source data, or convert semitone values to native/Web pitch representations. If validation fails, callers must preserve the existing non-AI path. The ±2-semitone default is an initial guardrail and must be reviewed against approved labels before any production use.
