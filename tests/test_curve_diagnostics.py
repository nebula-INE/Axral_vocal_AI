import pytest

from axral_vocal_ai.contracts import PitchDeltaPoint
from axral_vocal_ai.curve_diagnostics import audit_pitch_curve


def test_reports_smooth_curve_without_flags():
    report = audit_pitch_curve([
        PitchDeltaPoint(0.0, 0.0),
        PitchDeltaPoint(0.1, 0.2),
        PitchDeltaPoint(0.2, 0.4),
    ])
    assert report["status"] == "audited"
    assert report["point_count"] == 3
    assert report["segment_count"] == 2
    assert report["max_adjacent_jump_semitones"] == pytest.approx(0.2)
    assert report["max_slope_semitones_per_sec"] == pytest.approx(2.0)
    assert report["total_variation_semitones"] == pytest.approx(0.4)
    assert report["flagged_segment_count"] == 0


def test_flags_large_jump_and_fast_slope():
    report = audit_pitch_curve([
        {"time_sec": 0.0, "delta_semitones": 0.0},
        {"time_sec": 0.01, "delta_semitones": 0.5},
        {"time_sec": 0.2, "delta_semitones": 0.6},
    ])
    assert report["flagged_segment_count"] == 1
    assert report["flagged_segments"][0]["segment_index"] == 0
    assert report["flagged_segments"][0]["jump_semitones"] == pytest.approx(0.5)
    assert report["flagged_segments"][0]["slope_semitones_per_sec"] == pytest.approx(50.0)


def test_empty_and_single_point_curves_are_valid():
    assert audit_pitch_curve([])["segment_count"] == 0
    one = audit_pitch_curve([PitchDeltaPoint(1.0, -0.25)])
    assert one["max_adjacent_jump_semitones"] == 0.0
    assert one["flagged_segment_count"] == 0


@pytest.mark.parametrize("points", [
    [{"time_sec": 0.0, "delta_semitones": 0.0},
     {"time_sec": 0.0, "delta_semitones": 0.1}],
    [{"time_sec": 1.0, "delta_semitones": 0.0},
     {"time_sec": 0.5, "delta_semitones": 0.1}],
])
def test_rejects_duplicate_or_unordered_times(points):
    with pytest.raises(ValueError, match="strictly increasing"):
        audit_pitch_curve(points)


def test_rejects_non_finite_values_and_invalid_thresholds():
    with pytest.raises(ValueError, match="finite"):
        audit_pitch_curve([{"time_sec": 0.0, "delta_semitones": float("nan")}])
    with pytest.raises(ValueError, match="greater than zero"):
        audit_pitch_curve([], max_adjacent_jump_semitones=0)
    with pytest.raises(TypeError, match="must be numeric"):
        audit_pitch_curve([], max_slope_semitones_per_sec=True)
