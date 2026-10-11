import pytest

from axral_vocal_ai.training_data import DatasetValidationError, validate_records
from test_training_data import make_record


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
