import pytest

from axral_vocal_ai.contracts import PitchNote, PitchRequest
from axral_vocal_ai.curve_evaluation import audit_pitch_response_curves
from axral_vocal_ai.inference import PitchDeltaInferenceRuntime
from axral_vocal_ai.pitch_model import LinearPitchDeltaModel


def runtime(weights):
    return PitchDeltaInferenceRuntime(LinearPitchDeltaModel(weights=weights))


def test_curve_predictions_include_zero_samples_for_faithful_diagnostics():
    result = runtime((0.0, 0.0, 0.0, 0.0, 0.0)).predict_curve(
        PitchRequest(notes=(PitchNote(0.0, 1.0, 60, "a"),)),
        samples_per_note=3,
    )

    assert result.status == "ok"
    assert [point.time_sec for point in result.pitch_deltas] == pytest.approx(
        [0.25, 0.5, 0.75]
    )
    assert [point.delta_semitones for point in result.pitch_deltas] == [0.0, 0.0, 0.0]


def test_curve_audit_groups_points_per_note_and_does_not_cross_boundaries():
    model = runtime((0.0, 0.0, 0.0, 1.0, 0.0))
    request = PitchRequest(notes=(
        PitchNote(0.0, 1.0, 60, "a"),
        PitchNote(1.0, 2.0, 62, "i"),
    ))
    response = model.predict_curve(request, samples_per_note=3)

    report = audit_pitch_response_curves(
        request, response, max_slope_semitones_per_sec=0.1
    )

    assert report["status"] == "audited"
    assert report["eligible_note_count"] == 2
    assert report["per_note"]["0"]["diagnostics"]["point_count"] == 3
    assert report["per_note"]["1"]["diagnostics"]["point_count"] == 3
    assert report["flagged_segment_count"] == 4
    # Each note is evaluated independently: no segment spans t=1.0.
    assert all(
        segment["end_sec"] <= 1.0
        for segment in report["per_note"]["0"]["diagnostics"]["flagged_segments"]
    )
    assert all(
        segment["start_sec"] >= 1.0
        for segment in report["per_note"]["1"]["diagnostics"]["flagged_segments"]
    )


def test_curve_api_rejects_bad_sample_count():
    engine = runtime((0.0, 0.0, 0.0, 0.0, 0.0))
    request = PitchRequest(notes=(PitchNote(0.0, 1.0, 60, "a"),))
    with pytest.raises(ValueError, match="samples_per_note"):
        engine.predict_curve(request, samples_per_note=True)


def test_audit_excludes_overlapping_notes():
    request = PitchRequest(notes=(
        PitchNote(0.0, 1.5, 60, "a"),
        PitchNote(1.0, 2.0, 62, "i"),
        PitchNote(3.0, 4.0, 64, "u"),
    ))
    response = runtime((0.0, 0.0, 0.0, 0.5, 0.0)).predict_curve(
        request, samples_per_note=3
    )

    report = audit_pitch_response_curves(request, response)

    assert report["eligible_note_count"] == 1
    assert report["skipped_notes"] == [
        {"note_index": 0, "reason": "overlapping note intervals"},
        {"note_index": 1, "reason": "overlapping note intervals"},
    ]
    assert report["per_note"]["2"]["diagnostics"]["point_count"] == 3
