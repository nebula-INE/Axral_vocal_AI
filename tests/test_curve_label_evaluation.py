from axral_vocal_ai.contracts import PitchDeltaPoint, PitchNote, PitchRequest, PitchResponse
from axral_vocal_ai.curve_label_evaluation import evaluate_pitch_curve_against_labels


def test_curve_labels_interpolate_and_compare_zero_baseline():
    request = PitchRequest(notes=[PitchNote(0.0, 1.0, 60, "a")])
    response = PitchResponse(
        status="ok",
        pitch_deltas=(
            PitchDeltaPoint(0.25, 0.5),
            PitchDeltaPoint(0.5, 1.0),
            PitchDeltaPoint(0.75, 1.5),
        ),
    )
    result = evaluate_pitch_curve_against_labels(
        request, response,
        [
            {"time_sec": 0.375, "delta_semitones": 0.75},
            {"time_sec": 0.625, "delta_semitones": 0.0},
        ],
    )
    assert result["status"] == "evaluated"
    assert result["labels_evaluated"] == 2
    assert result["mae_semitones"] == 0.625
    assert result["zero_delta_baseline_mae_semitones"] == 0.375
    assert result["mae_improvement_over_zero_baseline_semitones"] == -0.25


def test_curve_label_outside_sample_bracket_is_skipped_without_extrapolation():
    request = PitchRequest(notes=[PitchNote(0.0, 1.0, 60, "a")])
    response = PitchResponse(
        status="ok",
        pitch_deltas=(PitchDeltaPoint(0.25, 0.5), PitchDeltaPoint(0.75, 1.5)),
    )
    result = evaluate_pitch_curve_against_labels(
        request, response, [{"time_sec": 0.1, "delta_semitones": 0.5}],
    )
    assert result["status"] == "insufficient_coverage"
    assert result["labels_evaluated"] == 0
    assert result["skipped_labels"][0]["reason"].startswith("not bracketed")


def test_curve_label_does_not_interpolate_across_note_boundaries():
    request = PitchRequest(notes=[
        PitchNote(0.0, 1.0, 60, "a"),
        PitchNote(1.0, 2.0, 62, "i"),
    ])
    response = PitchResponse(
        status="ok",
        pitch_deltas=(
            PitchDeltaPoint(0.5, 0.5),
            PitchDeltaPoint(1.5, 1.5),
        ),
    )
    result = evaluate_pitch_curve_against_labels(
        request, response, [{"time_sec": 1.0, "delta_semitones": 1.0}],
    )
    assert result["labels_evaluated"] == 0
    assert result["labels_skipped"] == 1


def test_curve_label_rejects_duplicate_timestamps():
    request = PitchRequest(notes=[PitchNote(0.0, 1.0, 60, "a")])
    response = PitchResponse(
        status="ok",
        pitch_deltas=(PitchDeltaPoint(0.25, 0.5), PitchDeltaPoint(0.75, 1.5)),
    )
    labels = [
        {"time_sec": 0.5, "delta_semitones": 1.0},
        {"time_sec": 0.5, "delta_semitones": 0.0},
    ]
    try:
        evaluate_pitch_curve_against_labels(request, response, labels)
    except ValueError as exc:
        assert "unique" in str(exc)
    else:
        raise AssertionError("duplicate timestamps must be rejected")
