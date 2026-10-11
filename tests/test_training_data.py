import json

import pytest

from axral_vocal_ai.training_data import DatasetValidationError, validate_jsonl, validate_records


def make_record(record_id="r1", bank="bank-a", split="train", permission="approved", target=None):
    return {
        "schema_version": 1,
        "record_id": record_id,
        "source_id": "source-a",
        "permission_status": permission,
        "license_id": "INTERNAL-ML-PERMISSION-001",
        "voicebank_id": bank,
        "split": split,
        "input": {
            "notes": [
                {"start_sec": 0.0, "end_sec": 0.4, "midi_note": 60, "lyric": "あ", "voiced": True}
            ]
        },
        "target": target,
        "provenance": {
            "acquisition_method": "curated fixture",
            "source_reference": "synthetic://fixture",
            "review_date": "2026-10-11",
            "review_status": "approved",
        },
        "preprocessing": {"tool_version": "fixture-1", "transformations": []},
    }


def make_target():
    return {
        "kind": "pitch_delta_semitones",
        "points": [
            {"time_sec": 0.0, "delta_semitones": 0.0},
            {"time_sec": 0.2, "delta_semitones": 0.25},
        ],
        "label_source": "synthetic_fixture",
        "confidence": 1.0,
    }


def test_manifest_validation_summarizes_voicebank_level_splits():
    summary = validate_records([
        make_record("train-1", "bank-a", "train", target=make_target()),
        make_record("valid-1", "bank-b", "validation", target=make_target()),
        make_record("test-1", "bank-c", "test", target=make_target()),
    ], require_labeled=True)

    assert summary["status"] == "valid"
    assert summary["records"] == 3
    assert summary["records_by_split"] == {"test": 1, "train": 1, "validation": 1}
    assert summary["voicebanks_by_split"]["test"] == ["bank-c"]


def test_manifest_rejects_unapproved_sources():
    with pytest.raises(DatasetValidationError, match="not approved"):
        validate_records([make_record(permission="review_required")])


def test_manifest_rejects_voicebank_leakage_across_splits():
    with pytest.raises(DatasetValidationError, match="multiple splits"):
        validate_records([
            make_record("a", "same-bank", "train"),
            make_record("b", "same-bank", "test"),
        ])


def test_training_mode_requires_labels():
    with pytest.raises(DatasetValidationError, match="target labels are required"):
        validate_records([make_record()], require_labeled=True)


def test_training_readiness_requires_three_voicebank_isolated_splits():
    with pytest.raises(DatasetValidationError, match="missing: validation, test"):
        validate_records([
            make_record("train-1", "bank-a", "train", target=make_target()),
        ], require_labeled=True)


def test_manifest_rejects_nonfinite_or_unordered_targets():
    target = make_target()
    target["points"][1]["delta_semitones"] = float("nan")
    with pytest.raises(DatasetValidationError, match="must be finite"):
        validate_records([make_record(target=target)])


def test_manifest_rejects_private_paths_and_audio_fields():
    record = make_record()
    record["provenance"]["audio_path"] = "/private/voicebank/a.wav"
    with pytest.raises(DatasetValidationError, match="not allowed"):
        validate_records([record])


def test_jsonl_cli_core_reads_metadata_without_audio(tmp_path):
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(json.dumps(make_record(target=make_target())) + "\n", encoding="utf-8")

    summary = validate_jsonl(manifest, require_labeled=True)

    assert summary["records"] == 1
    assert summary["require_labeled"] is True


def test_manifest_rejects_duplicate_record_ids():
    with pytest.raises(DatasetValidationError, match="duplicate record_id"):
        validate_records([make_record("duplicate"), make_record("duplicate", "bank-b", "test")])


def test_manifest_rejects_empty_dataset():
    with pytest.raises(DatasetValidationError, match="no records"):
        validate_records([])
