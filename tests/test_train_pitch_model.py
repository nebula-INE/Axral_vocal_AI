import pytest

from training.train_pitch_model import assess_validation


@pytest.mark.parametrize(
    ("improvement", "expected_status", "has_warning"),
    [
        (0.25, "better_than_zero_baseline", False),
        (0.0, "equal_to_zero_baseline", True),
        (-0.1, "worse_than_zero_baseline", True),
        (None, "unavailable", True),
    ],
)
def test_assess_validation_baseline_comparison(improvement, expected_status, has_warning):
    status, warnings = assess_validation({
        "validation": {
            "mae_improvement_over_zero_baseline_semitones": improvement,
        }
    })

    assert status == expected_status
    assert bool(warnings) is has_warning


def test_assess_validation_handles_missing_validation_metrics():
    status, warnings = assess_validation({})

    assert status == "unavailable"
    assert warnings
