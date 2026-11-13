"""Safety checks for the hosted Hugging Face audit workflow."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "hf-utau-voicebank-audit.yml"


def test_hosted_audit_is_manual_only_until_permission_review():
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in source
    assert "  schedule:" not in source
    assert "permission_reviewed:" in source
    assert 'default: "no"' in source
    assert "- name: Require explicit permission review for hosted processing" in source


def test_permission_gate_runs_before_checkout_and_hub_download():
    source = WORKFLOW.read_text(encoding="utf-8")

    gate = source.index("Require explicit permission review for hosted processing")
    checkout = source.index("Check out Axral Vocal AI")
    download = source.index("Download and audit VO-US")
    assert gate < checkout < download
    assert "PERMISSION_REVIEWED:" in source
    assert 'if [ "$PERMISSION_REVIEWED" != "yes" ]; then' in source


def test_hugging_face_token_is_scoped_to_the_download_step():
    source = WORKFLOW.read_text(encoding="utf-8")

    download = source.index("Download and audit VO-US")
    token = source.index("HF_TOKEN:")
    assert token > download
    assert "env:\n          HF_TOKEN:" in source[download:]
