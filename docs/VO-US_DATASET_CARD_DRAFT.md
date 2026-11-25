---
pretty_name: VO-US
tags:
  - utau
  - voicebank
  - axral
---

# VO-US

**VO-US** is a private dataset repository maintained for the Axral Vocal AI project. Its current role is to hold and organize UTAU voicebank archives used for compatibility research and voicebank-format auditing.

このリポジトリは、Axral Vocal AI プロジェクトで利用する UTAU 音源アーカイブを管理するための非公開データセットです。現段階では、学習用データセットとして整備済みであることや、収録音源の機械学習利用が許諾済みであることを意味しません。

## Repository status

- **Visibility:** Private.
- **Maintainer:** SEKOIA2900.
- **Observed revision:** The exact full Hub commit SHA has not yet been captured in the current audit.
- **Dataset format:** Individually packaged UTAU voicebank ZIP archives.
- **Dataset Viewer:** On 2026-11-25, the Hub page reported that the dataset was empty for Dataset Viewer purposes. No common loading configuration, examples, or train/evaluation splits have been defined.
- **Scope:** Voicebank archive catalog and compatibility/audit input. This repository is not currently presented as a unified, ready-to-train machine-learning dataset.

## Current archive inventory

The following files were visible in the repository's Files tab on 2026-11-25. Sizes are approximate UI-displayed values and may be rounded.

| Archive | Displayed size | Status |
|---|---:|---|
| `つくよみちゃんUTAU音源.zip` | about 479 MB | Stored archive; internal contents and permissions still require separate audit |
| `桃音モモSoft.zip` | about 107 MB | Stored archive; internal contents and permissions still require separate audit |
| `波音リツ連続音Ver1.5.1.zip` | about 277 MB | Stored archive; internal contents and permissions still require separate audit |

The Files page displayed approximately 863 MB total repository storage at the time of inspection. The existing archive paths and bytes should be preserved unless a separately reviewed migration is approved.

## Intended research and engineering uses

Subject to the rights and permissions applicable to each individual voicebank, the repository may support:

- Inspecting UTAU voicebank archive structure.
- Testing voicebank discovery and parsing, including `oto.ini` and `prefix.map` when present.
- Checking compatibility with Axral Vocal AI / VO-SE.
- Preparing separately approved metadata and audit manifests.

These are project goals, not a blanket grant of permission to process every archive for every purpose.

## Permissions, licensing, and responsible use

**No repository-wide license is declared here.** The archives may have different authors, sources, licenses, and usage conditions. The presence of an archive in this private repository does not establish permission for any particular use.

Before processing or using an individual voicebank, record and review its source and exact terms for each relevant activity:

- Local download and inspection.
- Hosted processing (for example, CI or cloud notebooks).
- Metadata extraction and derived-feature generation.
- Machine-learning training and evaluation.
- Commercial use of a resulting model.
- Distribution of model weights or checkpoints.
- Redistribution or delivery of the original archive or audio.

Until the applicable permissions have been verified, treat the relevant permission status as **review required**. Do not infer commercial-training, hosted-processing, model-distribution, or redistribution rights from public availability, private storage, or successful download.

Do not redistribute any source archive or audio unless the relevant rights holder and license explicitly permit it. Keep credentials and access tokens out of this repository.

## Data organization and loading

The repository currently contains individually packaged voicebank archives rather than a single normalized table or audio-example schema. The archives must remain independently identifiable.

No combined `train` or `test` split is declared. Do not load all voicebanks as one homogeneous training set. Any future machine-learning corpus should use source-specific manifests, provenance records, permission decisions, and explicit split definitions. Human singing corpora, speech-only material, synthetic examples, and UTAU voicebanks must remain distinguishable.

The Dataset Viewer state should be revisited only after a validated, documented data schema and explicit loading configuration are ready. Creating this card alone does not convert the ZIP archives into a normalized dataset or create training splits.

## Known limitations

- The visible file inventory is based on a screenshot taken on 2026-11-25; a full recursive Hub API/CLI listing and immutable revision SHA are still pending.
- Archive contents have not been verified by this card. Internal voicebank roots, file counts, sample rates, metadata encodings, and parser results must be established by a separate audit.
- Source attribution, exact license texts, performer/composition rights, and each voicebank's permitted uses must be recorded independently.
- No archive is marked as approved for commercial machine-learning training by this card.
- The repository is private; access is limited by the Hugging Face repository's access settings.

## Maintenance

When adding or changing an archive, update the inventory and record its source, immutable version or revision where available, checksum, license evidence, attribution, and permission decisions. Keep original archives unchanged during audit work. Store audit outputs separately from source data and avoid publishing sensitive metadata or raw audio in CI artifacts.

## Contact and project

This dataset is maintained as part of the Axral Vocal AI project:

- Project repository: https://github.com/nebula-INE/Axral_vocal_AI
- Dataset repository: https://huggingface.co/datasets/SEKOIA2900/VO-US

---

*This card documents the repository state observed on 2026-11-25. It should be updated when the full Hub inventory, archive audits, and source-specific permission records are available.*
