import copy

import pytest

from axral_vocal_ai.pitch_model import (
    FEATURE_NAMES,
    LinearPitchDeltaModel,
)


def valid_artifact():
    return LinearPitchDeltaModel(weights=(0.1, -0.2, 0.3, 0.0, 0.05)).to_dict()


def test_model_artifact_round_trip_preserves_bounded_prediction():
    original = LinearPitchDeltaModel(weights=(0.1, -0.2, 0.3, 0.0, 0.05))
    restored = LinearPitchDeltaModel.from_dict(original.to_dict())

    assert restored == original
    features = (1.0, 0.5, 0.25, 0.0625, 0.4)
    assert restored.predict_features(features) == pytest.approx(original.predict_features(features))


@pytest.mark.parametrize("field,value,match", [
    ("schema_version", 2, "schema_version"),
    ("model_type", "unknown", "model_type"),
    ("feature_version", 999, "feature_version"),
    ("feature_names", list(reversed(FEATURE_NAMES)), "feature_names"),
    ("target_kind", "midi_note", "target_kind"),
    ("safety", {}, "safety contract"),
    ("weights", [0.0], "feature count"),
    ("weights", [0.0, 0.0, 0.0, 0.0, float("nan")], "finite"),
    ("weights", [0.0, 0.0, 0.0, 0.0, True], "numeric"),
])
def test_model_artifact_rejects_incompatible_or_unsafe_payload(field, value, match):
    payload = copy.deepcopy(valid_artifact())
    payload[field] = value

    with pytest.raises(ValueError, match=match):
        LinearPitchDeltaModel.from_dict(payload)


def test_model_artifact_requires_object_payload():
    with pytest.raises(ValueError, match="must be an object"):
        LinearPitchDeltaModel.from_dict(None)
