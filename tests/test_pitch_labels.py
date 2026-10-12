import pytest

from axral_vocal_ai.pitch_labels import (
    PitchLabelError,
    build_pitch_delta_labels,
    make_training_target,
)


def track(pitches, *, voiced=None, confidence=None, times=None):
    times = times if times is not None else [index * 0.01 for index in range(len(pitches))]
    voiced = voiced if voiced is not None else [True] * len(pitches)
    points = []
    for index, pitch in enumerate(pitches):
        point = {"time_sec": times[index], "voiced": voiced[index]}
        if pitch is not None:
            point["pitch_semitones"] = pitch
        if confidence is not None:
            point["confidence"] = confidence[index]
        points.append(point)
    return points


def test_builds_target_minus_reference_without_rounding():
    labels = build_pitch_delta_labels(track([60.0, 61.25]), track([60.5, 61.0]))
    assert labels == [
        {"time_sec": 0.0, "delta_semitones": 0.5},
        {"time_sec": 0.01, "delta_semitones": -0.25},
    ]


def test_skips_unvoiced_pairs_without_interpolating_across_gap():
    labels = build_pitch_delta_labels(
        track([60.0, None, 62.0], voiced=[True, False, True]),
        track([60.25, None, 62.5], voiced=[True, False, True]),
    )
    assert labels == [
        {"time_sec": 0.0, "delta_semitones": 0.25},
        {"time_sec": 0.02, "delta_semitones": 0.5},
    ]


def test_confidence_threshold_requires_confidence_and_skips_low_confidence():
    ref = track([60.0, 61.0], confidence=[0.9, 0.4])
    tgt = track([60.25, 61.25], confidence=[0.8, 0.95])
    assert build_pitch_delta_labels(ref, tgt, min_confidence=0.7) == [
        {"time_sec": 0.0, "delta_semitones": 0.25}
    ]
    with pytest.raises(PitchLabelError, match="confidence is required"):
        build_pitch_delta_labels(track([60.0]), track([60.1]), min_confidence=0.5)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), True])
def test_rejects_nonfinite_or_boolean_pitch_values(bad):
    with pytest.raises(PitchLabelError):
        build_pitch_delta_labels(track([60.0]), track([bad]))


@pytest.mark.parametrize("delta", [-2.01, 2.01])
def test_rejects_out_of_contract_delta_instead_of_clipping(delta):
    with pytest.raises(PitchLabelError, match="outside"):
        build_pitch_delta_labels(track([60.0]), track([60.0 + delta]))


def test_rejects_mismatched_time_grids():
    with pytest.raises(PitchLabelError, match="time-grid mismatch"):
        build_pitch_delta_labels(
            track([60.0, 61.0], times=[0.0, 0.01]),
            track([60.0, 61.0], times=[0.0, 0.02]),
        )


def test_rejects_duplicate_or_unordered_timestamps():
    with pytest.raises(PitchLabelError, match="strictly increasing"):
        build_pitch_delta_labels(
            track([60.0, 61.0], times=[0.0, 0.0]),
            track([60.0, 61.0], times=[0.0, 0.01]),
        )


def test_rejects_empty_or_different_length_tracks():
    assert build_pitch_delta_labels([], []) == []
    with pytest.raises(PitchLabelError, match="same time grid"):
        build_pitch_delta_labels(track([60.0]), track([60.0, 61.0]))



def test_packages_built_labels_in_training_manifest_target_schema():
    labels = build_pitch_delta_labels(track([60.0, 61.0]), track([60.25, 60.75]))
    target = make_training_target(
        labels,
        label_source="reviewed_pitch_track_v1",
        confidence=0.9,
    )

    assert target == {
        "kind": "pitch_delta_semitones",
        "points": [
            {"time_sec": 0.0, "delta_semitones": 0.25},
            {"time_sec": 0.01, "delta_semitones": -0.25},
        ],
        "label_source": "reviewed_pitch_track_v1",
        "confidence": 0.9,
    }


@pytest.mark.parametrize("label_source", ["", "   ", None])
def test_training_target_requires_label_source(label_source):
    with pytest.raises(PitchLabelError, match="label_source"):
        make_training_target(
            [{"time_sec": 0.0, "delta_semitones": 0.0}],
            label_source=label_source,
        )


def test_training_target_rejects_empty_labels_and_bad_confidence():
    with pytest.raises(PitchLabelError, match="at least one"):
        make_training_target([], label_source="reviewed")
    with pytest.raises(PitchLabelError, match=r"confidence must be in"):
        make_training_target(
            [{"time_sec": 0.0, "delta_semitones": 0.0}],
            label_source="reviewed",
            confidence=1.1,
        )


@pytest.mark.parametrize(
    "labels",
    [
        [{"time_sec": 0.0, "delta_semitones": 0.0},
         {"time_sec": 0.0, "delta_semitones": 0.1}],
        [{"time_sec": -0.1, "delta_semitones": 0.0}],
        [{"time_sec": 0.0, "delta_semitones": 2.1}],
    ],
)
def test_training_target_rejects_invalid_points(labels):
    with pytest.raises(PitchLabelError):
        make_training_target(labels, label_source="reviewed")
