import json

import pytest

from axral_vocal_ai.training_data import DatasetValidationError, validate_jsonl, validate_records


def make_record(record_id="r1", bank="bank-a", split="train", permission="approved", target=None):
    return {
        "schema_version": 1,
        "record_id": record_id,
        "source_id": record_id,
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


def test_manifest_rejects_source_leakage_across_splits():
    first = make_record("train-1", "bank-a", "train")
    second = make_record("test-1", "bank-b", "test")
    second["source_id"] = first["source_id"]

    with pytest.raises(DatasetValidationError, match="source .* appears in multiple splits"):
        validate_records([first, second])


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
    rows = [
        make_record("train-1", "bank-a", "train", target=make_target()),
        make_record("validation-1", "bank-b", "validation", target=make_target()),
        make_record("test-1", "bank-c", "test", target=make_target()),
    ]
    manifest.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    summary = validate_jsonl(manifest, require_labeled=True)

    assert summary["records"] == 3
    assert summary["labeled_records"] == 3
    assert summary["require_labeled"] is True


def test_manifest_rejects_duplicate_record_ids():
    with pytest.raises(DatasetValidationError, match="duplicate record_id"):
        validate_records([make_record("duplicate"), make_record("duplicate", "bank-b", "test")])


def test_manifest_rejects_empty_dataset():
    with pytest.raises(DatasetValidationError, match="no records"):
        validate_records([])



def test_manifest_summary_counts_only_records_with_labels():
    summary = validate_records([
        make_record("labeled", "bank-a", "train", target=make_target()),
        make_record("unlabeled", "bank-b", "validation", target=None),
    ])
    assert summary["records"] == 2
    assert summary["labeled_records"] == 1


@pytest.mark.parametrize("field", [
    "audio_file", "waveform", "file_path", "source_path", "relative_path", "Audio_File",
])
def test_manifest_rejects_additional_payload_and_path_fields(field):
    record = make_record()
    record["provenance"][field] = "private-reference"
    with pytest.raises(DatasetValidationError, match="not allowed"):
        validate_records([record])


@pytest.mark.parametrize("path", [
    r"C:\\private\\voicebank\\a.wav",
    r"\\\\server\\share\\voicebank.wav",
])
def test_manifest_rejects_windows_filesystem_paths(path):
    record = make_record()
    record["provenance"]["source_reference"] = path
    with pytest.raises(DatasetValidationError, match="Windows filesystem path"):
        validate_records([record])

@pytest.mark.parametrize("delta", [-2.01, 2.01])
def test_manifest_rejects_training_deltas_outside_safe_range(delta):
    target = make_target()
    target["points"][1]["delta_semitones"] = delta
    with pytest.raises(DatasetValidationError, match=r"within \+/-2.0 semitones"):
        validate_records([make_record(target=target)])


@pytest.mark.parametrize("delta", [-2.0, 2.0])
def test_manifest_accepts_training_delta_at_safe_range_boundary(delta):
    target = make_target()
    target["points"][1]["delta_semitones"] = delta
    summary = validate_records([make_record(target=target)])
    assert summary["status"] == "valid"




@pytest.mark.parametrize(
    ("start_sec", "end_sec"),
    [
        (-0.01, 0.4),
        (0.3, 0.2),
        (float("nan"), 0.4),
        (0.0, float("inf")),
    ],
)
def test_manifest_rejects_invalid_note_time_bounds(start_sec, end_sec):
    record = make_record()
    record["input"]["notes"][0]["start_sec"] = start_sec
    record["input"]["notes"][0]["end_sec"] = end_sec

    with pytest.raises(DatasetValidationError):
        validate_records([record])


@pytest.mark.parametrize("split", ["", "testing", "dev", None])
def test_manifest_rejects_unknown_split_names(split):
    record = make_record(split=split)

    with pytest.raises(DatasetValidationError, match="split must be train, validation, or test"):
        validate_records([record])


@pytest.mark.parametrize("delta", [True, False])
def test_manifest_rejects_boolean_pitch_deltas(delta):
    target = make_target()
    target["points"][1]["delta_semitones"] = delta

    with pytest.raises(DatasetValidationError, match="must be numeric"):
        validate_records([make_record(target=target)])
