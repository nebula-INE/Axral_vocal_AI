"""Safety checks for the hosted Hugging Face audit workflow."""

import re
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

def test_all_workflow_actions_are_pinned_to_full_commit_shas():
    workflow_paths = (
        ROOT / ".github" / "workflows" / "tests.yml",
        WORKFLOW,
    )
    for workflow_path in workflow_paths:
        source = workflow_path.read_text(encoding="utf-8")
        references = re.findall(
            r"^\\s*uses:\\s*([^\\s]+)", source, flags=re.MULTILINE
        )
        assert references, workflow_path
        assert all(
            re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}", reference)
            for reference in references
        ), workflow_path

    audit_source = WORKFLOW.read_text(encoding="utf-8")
    assert "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7" in audit_source
    assert "actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0 # v7" in audit_source
    assert "actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7" in audit_source
