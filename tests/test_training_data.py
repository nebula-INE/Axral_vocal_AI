import json

import pytest

import axral_vocal_ai.training_data as training_data
from axral_vocal_ai.training_data import DatasetValidationError, validate_jsonl, validate_records


def make_record(record_id="r1", bank="bank-a", split="train", permission="approved", target=None):
    return {
        "schema_version": 1,
        "record_id": record_id,
        "source_id": record_id,
        "permission_status": permission,
        "license_id": "INTERNAL-ML-PERMISSION-001",
        "permissions": {
            "local_processing": "approved",
            "hosted_processing": "approved",
            "feature_extraction": "approved",
            "ml_training": "approved",
            "model_distribution": "review_required",
            "audio_redistribution": "prohibited",
        },
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


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("manifest byte limit exceeded (10)", "manifest_size_limit"),
        ("line 3: JSONL line byte limit exceeded (10)", "manifest_line_size_limit"),
        ("manifest record limit exceeded (10)", "manifest_record_limit"),
        ("line 2: manifest must be valid UTF-8", "manifest_invalid_encoding"),
        ("line 2: invalid JSON: bad", "manifest_invalid_json"),
        ("line 1: duplicate record_id 'PRIVATE_ID'", "duplicate_record_id"),
        ("line 2: source 'PRIVATE_SOURCE' appears in multiple splits", "split_leakage"),
        ("training readiness requires non-empty test split", "split_requirements_not_met"),
        ("line 1: source is not approved for ML use", "source_permission_not_approved"),
        ("line 1: permission scope hosted_processing is not approved", "source_permission_not_approved"),
        ("line 1: provenance review_status must be approved", "provenance_not_approved"),
        ("line 1: record.audio_path is not allowed in a metadata manifest", "private_payload_rejected"),
        ("line 1: input.notes[0].midi_note must be numeric", "invalid_note_data"),
        ("line 1: target.points must be a non-empty list", "invalid_or_missing_pitch_labels"),
        ("unexpected schema failure", "manifest_validation_failed"),
    ],
)
def test_validation_error_codes_are_stable_and_do_not_echo_private_details(message, expected):
    code = training_data.validation_error_code(DatasetValidationError(message))
    assert code == expected
    assert "PRIVATE" not in code


def test_manifest_rejects_unapproved_sources():
    with pytest.raises(DatasetValidationError, match="not approved"):
        validate_records([make_record(permission="review_required")])



def test_labeled_manifest_requires_explicit_permission_scopes():
    record = make_record(target=make_target())
    del record["permissions"]

    with pytest.raises(DatasetValidationError, match="permissions object is required"):
        validate_records([record], require_labeled=True)


@pytest.mark.parametrize("scope", ["feature_extraction", "ml_training", "local_processing"])
def test_local_training_requires_each_relevant_permission_scope(scope):
    record = make_record(target=make_target())
    record["permissions"][scope] = "review_required"

    with pytest.raises(DatasetValidationError, match=f"permission scope {scope} is not approved"):
        validate_records([record], require_labeled=True, execution_context="local")


def test_hosted_training_requires_explicit_cloud_processing_permission():
    record = make_record(target=make_target())
    record["permissions"]["hosted_processing"] = "review_required"

    with pytest.raises(DatasetValidationError, match="permission scope hosted_processing is not approved"):
        validate_records([record], require_labeled=True, execution_context="hosted")


def test_hosted_training_allows_unapproved_distribution_scopes_without_granting_them():
    rows = [
        make_record("train-1", "bank-a", "train", target=make_target()),
        make_record("valid-1", "bank-b", "validation", target=make_target()),
        make_record("test-1", "bank-c", "test", target=make_target()),
    ]
    summary = validate_records(rows, require_labeled=True, execution_context="hosted")

    assert summary["status"] == "valid"
    assert summary["execution_context"] == "hosted"
    assert rows[0]["permissions"]["model_distribution"] == "review_required"
    assert rows[0]["permissions"]["audio_redistribution"] == "prohibited"


def test_labeled_manifest_rejects_unknown_execution_context():
    record = make_record(target=make_target())

    with pytest.raises(DatasetValidationError, match="execution_context must be local or hosted"):
        validate_records([record], require_labeled=True, execution_context="kaggle")

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


def test_jsonl_reader_accepts_utf8_bom(tmp_path):
    manifest = tmp_path / "manifest.jsonl"
    row = make_record("bom-row", "bank-bom", "train", target=make_target())
    manifest.write_text("\ufeff" + json.dumps(row) + "\n", encoding="utf-8")

    summary = validate_jsonl(manifest)

    assert summary["status"] == "valid"
    assert summary["records"] == 1


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
        (0.2, 0.2),
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


@pytest.mark.parametrize(
    ("first_time", "second_time"),
    [
        (-0.01, 0.2),
        (0.2, 0.1),
        (0.0, float("nan")),
        (0.0, float("inf")),
    ],
)
def test_manifest_rejects_invalid_target_timestamps(first_time, second_time):
    target = make_target()
    target["points"][0]["time_sec"] = first_time
    target["points"][1]["time_sec"] = second_time

    with pytest.raises(DatasetValidationError):
        validate_records([make_record(target=target)])


@pytest.mark.parametrize("midi_note", [True, False, -0.1, 127.1, float("nan")])
def test_manifest_rejects_invalid_midi_note_values(midi_note):
    record = make_record()
    record["input"]["notes"][0]["midi_note"] = midi_note

    with pytest.raises(DatasetValidationError):
        validate_records([record])


@pytest.mark.parametrize("confidence", [True, False, -0.01, 1.01, float("nan"), float("inf")])
def test_manifest_rejects_invalid_label_confidence(confidence):
    target = make_target()
    target["confidence"] = confidence

    with pytest.raises(DatasetValidationError):
        validate_records([make_record(target=target)])



def test_manifest_allows_target_at_final_note_endpoint():
    target = make_target()
    target["points"][1]["time_sec"] = 0.4

    summary = validate_records([make_record(target=target)])

    assert summary["status"] == "valid"


def test_manifest_rejects_target_after_final_note_endpoint():
    target = make_target()
    target["points"][1]["time_sec"] = 0.41

    with pytest.raises(DatasetValidationError, match="must not exceed the note timeline end"):
        validate_records([make_record(target=target)])


def test_manifest_allows_target_at_first_note_endpoint():
    target = make_target()
    target["points"][0]["time_sec"] = 0.0

    summary = validate_records([make_record(target=target)])

    assert summary["status"] == "valid"


def test_manifest_rejects_target_before_first_note_start():
    record = make_record(target=make_target())
    record["input"]["notes"][0]["start_sec"] = 0.1

    with pytest.raises(DatasetValidationError, match="must not precede the note timeline start"):
        validate_records([record])


def test_manifest_rejects_duplicate_target_timestamps():
    target = make_target()
    target["points"][1]["time_sec"] = target["points"][0]["time_sec"]

    with pytest.raises(DatasetValidationError, match="strictly increasing"):
        validate_records([make_record(target=target)])

def test_manifest_rejects_numeric_values_that_overflow_float_conversion():
    record = make_record()
    record["input"]["notes"][0]["midi_note"] = 10**10000

    with pytest.raises(DatasetValidationError, match="must be finite"):
        validate_records([record])


def test_validate_jsonl_passes_a_streaming_iterator_to_record_validation(tmp_path, monkeypatch):
    manifest = tmp_path / "streamed.jsonl"
    rows = [
        make_record("train", "bank-a", "train", target=make_target()),
        make_record("validation", "bank-b", "validation", target=make_target()),
        make_record("test", "bank-c", "test", target=make_target()),
    ]
    manifest.write_text(
        chr(10).join(json.dumps(row, ensure_ascii=False) for row in rows) + chr(10),
        encoding="utf-8",
    )
    original = training_data.validate_records
    observed = {}

    def inspect_iterator(records, require_labeled=False, execution_context="local"):
        observed["is_list"] = isinstance(records, list)
        observed["is_iterator"] = iter(records) is records
        observed["execution_context"] = execution_context
        return original(
            records, require_labeled=require_labeled,
            execution_context=execution_context,
        )

    monkeypatch.setattr(training_data, "validate_records", inspect_iterator)

    summary = validate_jsonl(manifest, require_labeled=True)

    assert observed == {"is_list": False, "is_iterator": True, "execution_context": "local"}
    assert summary["records"] == 3


def test_jsonl_reader_rejects_oversized_manifest_before_parsing(tmp_path, monkeypatch):
    manifest = tmp_path / "oversized.jsonl"
    manifest.write_text(" " * 32, encoding="utf-8")
    monkeypatch.setattr(training_data, "MAX_MANIFEST_BYTES", 16)

    with pytest.raises(DatasetValidationError, match="manifest byte limit exceeded"):
        validate_jsonl(manifest)


def test_jsonl_reader_rejects_oversized_single_line(tmp_path, monkeypatch):
    manifest = tmp_path / "long-line.jsonl"
    manifest.write_text(json.dumps(make_record()) + "\n", encoding="utf-8")
    monkeypatch.setattr(training_data, "MAX_MANIFEST_BYTES", 1024 * 1024)
    monkeypatch.setattr(training_data, "MAX_JSONL_LINE_BYTES", 64)

    with pytest.raises(DatasetValidationError, match="JSONL line byte limit exceeded"):
        validate_jsonl(manifest)


def test_manifest_record_count_is_bounded_for_stream_and_iterable(monkeypatch):
    monkeypatch.setattr(training_data, "MAX_MANIFEST_RECORDS", 2)
    rows = [
        make_record("one", "bank-a", "train"),
        make_record("two", "bank-b", "validation"),
        make_record("three", "bank-c", "test"),
    ]

    with pytest.raises(DatasetValidationError, match="manifest record limit exceeded"):
        validate_records(iter(rows))
