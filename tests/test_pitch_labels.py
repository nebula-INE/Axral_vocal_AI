import pytest

from axral_vocal_ai.pitch_labels import PitchLabelError, build_pitch_delta_labels


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
