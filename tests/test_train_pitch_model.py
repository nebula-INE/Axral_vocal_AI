import math

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


@pytest.mark.parametrize("improvement", [math.nan, math.inf, -math.inf, "0.2", True])
def test_assess_validation_rejects_non_finite_or_non_numeric_improvement(improvement):
    status, warnings = assess_validation({
        "validation": {
            "mae_improvement_over_zero_baseline_semitones": improvement,
        }
    })

    assert status == "unavailable"
    assert warnings


from types import SimpleNamespace

from training.train_pitch_model import build_label_quality_report


def test_label_quality_report_exposes_skip_rates_by_split_and_voicebank():
    records = [
        {"voicebank_id": "bank-a", "split": "train", "target": {"points": [{}, {}, {}]}},
        {"voicebank_id": "bank-b", "split": "validation", "target": {"points": [{}, {}]}},
        {"voicebank_id": "bank-c", "split": "test", "target": {"points": [{}]}},
    ]
    examples = [
        SimpleNamespace(split="train", voicebank_id="bank-a"),
        SimpleNamespace(split="train", voicebank_id="bank-a"),
        SimpleNamespace(split="validation", voicebank_id="bank-b"),
    ]
    counts = {"labels_seen": 6, "labels_used": 3, "labels_without_voiced_note": 3}

    report = build_label_quality_report(records, counts, examples)

    assert report["overall"]["label_use_rate"] == pytest.approx(0.5)
    assert report["overall"]["label_skip_rate"] == pytest.approx(0.5)
    assert report["by_split"]["train"]["label_use_rate"] == pytest.approx(2 / 3)
    assert report["by_split"]["validation"]["label_use_rate"] == pytest.approx(0.5)
    assert report["by_split"]["test"]["label_use_rate"] == 0.0
    assert report["by_voicebank"]["bank-a"]["train"]["labels_not_mapped"] == 1
    assert "does not measure acoustic correctness" in report["definition"]


def test_label_quality_report_handles_no_labels_without_division_by_zero():
    report = build_label_quality_report(
        [{"voicebank_id": "bank-a", "split": "train", "target": None}],
        {"labels_seen": 0, "labels_used": 0, "labels_without_voiced_note": 0},
        [],
    )
    assert report["overall"]["label_use_rate"] is None
    assert report["overall"]["label_skip_rate"] is None
    assert report["by_split"]["train"]["label_use_rate"] is None


def test_target_distribution_reports_skew_and_summary_statistics():
    from training.train_pitch_model import build_target_distribution_report

    records = [
        {"voicebank_id": "bank-a", "split": "train", "target": {"points": [
            {"delta_semitones": -1.0}, {"delta_semitones": 0.0}, {"delta_semitones": 2.0},
        ]}},
        {"voicebank_id": "bank-b", "split": "validation", "target": {"points": [
            {"delta_semitones": 1.0},
        ]}},
    ]
    report = build_target_distribution_report(records)

    overall = report["overall"]
    assert overall["count"] == 4
    assert overall["mean"] == pytest.approx(0.5)
    assert overall["median"] == pytest.approx(0.5)
    assert overall["min"] == -1.0
    assert overall["max"] == 2.0
    assert overall["positive_count"] == 2
    assert overall["negative_count"] == 1
    assert overall["zero_count"] == 1
    assert report["by_split"]["train"]["count"] == 3
    assert report["by_voicebank"]["bank-b"]["mean"] == 1.0
    assert "do not measure label correctness" in report["definition"]


def test_target_distribution_handles_empty_groups():
    from training.train_pitch_model import build_target_distribution_report

    report = build_target_distribution_report([
        {"voicebank_id": "bank-empty", "split": "train", "target": {"points": []}},
    ])
    assert report["overall"]["count"] == 0
    assert report["overall"]["mean"] is None
    assert report["by_split"]["train"]["p10"] is None
    assert report["by_voicebank"]["bank-empty"]["zero_count"] == 0
