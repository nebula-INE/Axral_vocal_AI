# Axral Vocal AI

Universal Singing AI research and implementation repository for the Axral / VO-SE ecosystem.

## Purpose

Develop a shared AI layer for singing-expression assistance that can work with diverse UTAU voicebanks without requiring a separate AI model for each voicebank.

This repository is intended for AI-specific source code, training/evaluation tools, model interfaces, and technical documentation. The existing VO-SE_vocal renderer remains the source of truth for UTAU-compatible rendering unless a separately reviewed design explicitly changes that boundary.

## Core principles

- Preserve existing UTAU voicebank compatibility.
- Keep AI optional: disabling AI must leave the established rendering path available.
- Normalize voicebank and phoneme information before model inference.
- Separate training code, inference/runtime code, datasets, and exported model artifacts.
- Do not commit voicebank audio, datasets, checkpoints, secrets, or other restricted assets without checking permissions and repository policy.
- Evaluate unseen voicebanks, not only voicebanks used for training.
- Make changes incrementally and validate audio quality before integration.

## Initial implementation order

1. Audit the existing VO-SE_vocal AI, voicebank parsing, PrefixMap, phoneme/alias resolution, and pitch editing interfaces.
2. Define versioned input/output contracts for AI inference.
3. Implement voicebank profile extraction and canonical phoneme mapping.
4. Build a non-destructive pitch-expression MVP behind an opt-in feature flag.
5. Prepare permitted training/evaluation data and a reproducible training pipeline.
6. Evaluate quality, compatibility, runtime, and memory use before adding more expression heads.

## Repository layout

- `docs/`: architecture, data contracts, and implementation decisions
- `src/axral_vocal_ai/`: inference/runtime package
- `training/`: dataset preparation, training, and evaluation tooling
- `tests/`: unit, integration, and regression tests
- `models/`: model manifests and documentation; large model artifacts should use an explicit artifact-storage policy

The exact structure may evolve after the initial code audit. Avoid duplicating existing VO-SE_vocal functionality until its interfaces have been reviewed.
