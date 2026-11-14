"""Structural checks for the voicebank permission register template."""

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "docs" / "voicebank_permission_register.template.csv"


def test_permission_register_has_independent_hosted_provider_scopes():
    with REGISTER.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)

    required_columns = {
        "hosted_processing",
        "github_actions_processing",
        "kaggle_processing",
        "local_processing",
        "feature_extraction",
        "ml_training",
        "model_distribution",
        "audio_redistribution",
    }
    assert required_columns.issubset(reader.fieldnames or [])
    assert len(rows) == 4
    for row in rows:
        assert row["exact_release"] == "not_identified"
        assert row["review_status"] == "not_started"
        for column in required_columns:
            assert row[column] == "review_required"


def test_provider_scope_guidance_requires_broad_and_platform_approval():
    guidance = (ROOT / "docs" / "real_voicebank_validation.md").read_text(encoding="utf-8")

    assert "`hosted_processing` and `github_actions_processing`" in guidance
    assert "`hosted_processing` and `kaggle_processing`" in guidance
    assert "Approval for one provider does not imply approval for the other." in guidance
    assert "neither reads or validates the register automatically" in guidance
