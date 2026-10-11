import pytest

from axral_vocal_ai.training_data import DatasetValidationError, validate_records


def make_record(permission="approved", split="train"):
    return {
        "schema_version": 1,
        "record_id": "r1",
        "source_id": "source-1",
        "permission_status": permission,
        "license_id": "fixture-license",
        "voicebank_id": "bank-a",
        "split": split,
        "input": {"notes": [{"start_sec": 0.0, "end_sec": 0.4, "midi_note": 60, "lyric": "あ"}]},
        "target": None,
        "provenance": {
            "acquisition_method": "synthetic fixture",
            "source_reference": "synthetic://fixture",
            "review_date": "2026-10-11",
            "review_status": "approved",
        },
        "preprocessing": {"tool_version": "fixture-1", "transformations": []},
    }


@pytest.mark.parametrize("permission", [None, 1, [], {}, True])
def test_manifest_rejects_non_string_permission_status(permission):
    record = make_record(permission=permission)
    with pytest.raises(DatasetValidationError, match="invalid permission_status"):
        validate_records([record])


@pytest.mark.parametrize("split", [[], {}, 1, True])
def test_manifest_rejects_non_string_split(split):
    record = make_record(split=split)
    with pytest.raises(DatasetValidationError, match="split must be train, validation, or test"):
        validate_records([record])
