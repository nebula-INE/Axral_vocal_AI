"""Structural checks for the single-cell Kaggle notebook."""
import ast
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "kaggle" / "Axral_Vocal_AI_OneCell.ipynb"


def test_trusted_axral_origin_accepts_only_single_canonical_remote():
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    source = "".join(
        "".join(cell["source"]) for cell in notebook["cells"]
        if cell.get("cell_type") == "code"
    )
    tree = ast.parse(source)
    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "is_trusted_axral_origin"
    )
    isolated = ast.Module(body=[function], type_ignores=[])
    namespace = {}
    exec(compile(isolated, str(NOTEBOOK), "exec"), namespace)
    is_trusted = namespace["is_trusted_axral_origin"]

    assert is_trusted(["https://github.com/nebula-INE/Axral_vocal_AI.git"])
    assert is_trusted(["git@github.com:nebula-INE/Axral_vocal_AI.git"])
    assert is_trusted(["ssh://git@github.com/nebula-INE/Axral_vocal_AI"])
    assert not is_trusted(["https://github.com/another-owner/untrusted.git"])
    assert not is_trusted(["https://github.com/nebula-INE/Axral_vocal_AI.git", "https://evil.example/repo.git"])
    assert not is_trusted(["https://github.com/nebula-INE/Axral_vocal_AI.git/"])


def test_kaggle_notebook_is_valid_json_and_has_one_executable_cell():
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    assert notebook["nbformat"] == 4
    code_cells = [cell for cell in notebook["cells"] if cell.get("cell_type") == "code"]
    assert len(code_cells) == 1
    source = "".join(code_cells[0]["source"])
    ast.parse(source)
    assert 'HF_DATA_URL = "https://huggingface.co/datasets/' in source
    assert "validate_jsonl(manifest, require_labeled=True)" in source
    assert "validation_error_code(exc)" in source
    assert "training/train_pitch_model.py" in source
    assert "resume_download" not in source
    assert "scripts/kaggle_hf_download.py" in source
    assert "download_summary.json" in source
    assert "discover_voicebank_roots" in source
    assert "snapshot_download" not in source  # download logic lives in the tested helper
    assert 'if DATA_ROOT.exists(): shutil.rmtree(DATA_ROOT)' in source
    assert 'DATA_ROOT = Path("/kaggle/temp/hf_voicebanks")' in source
    assert "shutil.rmtree(DATA_ROOT, ignore_errors=True)" in source
    assert "TEMP_DATA_CLEANED" in source
    assert "sanitize_dataset_paths" in source
    assert "redact_output=False" in source
    assert "detailed dataset output suppressed" in source
    assert "safe_command_diagnostic(p.stdout)" in source
    assert "safe diagnostic=" in source
    assert "output_tail=0, redact_output=True" in source

    audit_start = source.index("audit_rc = run")
    audit_end = source.index("audit_results.append", audit_start)
    assert "redact_output=True" in source[audit_start:audit_end]
    assert '"training/validate_dataset.py"' not in source
    assert 'private_model_report = DATA_ROOT / "model_reports" / "pitch_delta_report.json"' in source
    assert 'public_model_report = OUT / "models" / "pitch_delta_metrics.json"' in source
    assert "build_public_model_report(private_report)" in source
    assert 'OUT / "models" / "pitch_delta_metrics.json"' in source
    assert 'OUT / "models" / "pitch_delta_report.json"' not in source
    assert 'str(model_report)' not in source
    assert "manifest_index" in source
    assert "re.escape(str(DATA_ROOT))" in source and '"<dataset-path>"' in source
    assert 'r"[^\\r\\n]*"' in source  # redact full paths even when they contain spaces
    assert 'audit_dir = DATA_ROOT / "audit_reports"' in source
    assert "build_public_download_summary(download_summary)" in source
    assert 'public_download_summary.get("dataset_card_license")' in source
    assert 'dataset_id = public_download_summary.get("dataset")' in source
    assert 'str(download_summary.get("dataset_card_license")' not in source
    assert '"download": public_download_summary' in source
    assert '"manifest_index": manifest_index' in source
    assert '"manifest_validation_failure_codes": validation_failure_codes' in source
    assert '"training_diagnostic_code": training_diagnostic_code' in source
    assert "manifest_not_found" in source
    assert "no_eligible_labelled_manifest" in source
    assert "manifest validation failure codes" in source.lower()
    assert "artifact_files = [" in source
    assert 'OUT / "voicebank_audit_summary.json"' in source
    assert 'OUT / "models" / "pitch_delta_metrics.json"' in source
    assert 'for artifact in OUT.rglob("*")' not in source
    assert 'OUT / "audits"' not in source
    assert source.index("TEMP_DATA_CLEANED") < source.index("with zipfile.ZipFile(archive")
    assert "sys.path.insert(0, str(PROJECT))" in source
    assert "audit_results = []" in source
    audit_start = source.index("audit_rc = run")
    audit_end = source.index("audit_results.append", audit_start)
    assert "redact_output=True" in source[audit_start:audit_end]
    assert "blocked_voicebank_audit_findings" in source
    assert '"audit_failures": audit_failures' in source
    assert '(OUT / "download_summary.json").write_text' in source
    assert "license/readme documents indexed" in source
    assert '["git", "status", "--porcelain"]' in source
    assert '["git", "remote", "get-url", "--all", "origin"]' in source
    assert "is_trusted_axral_origin(origin_urls)" in source
    assert "Existing checkout origin is not the trusted Axral_vocal_AI GitHub repository" in source
    assert source.index("origin_result = subprocess.run") < source.index('["git", "fetch", "--depth", "1", "origin", "main"]')
    assert '["git", "fetch", "--depth", "1", "origin", "main"]' in source
    assert "required_pipeline_files" in source
    assert '["git", "fetch", "--depth", "1", "origin", "feat/kaggle-one-url-pipeline"]' in source
    assert "Default branch does not contain the Kaggle pipeline helpers yet" in source
    assert "Axral checkout is missing required Kaggle pipeline files" in source
    assert '["git", "reset", "--hard", "FETCH_HEAD"]' in source
    assert "local changes" in source
    assert "source_commit" in source
    assert "MAX_MANIFEST_BYTES" in source
    assert "MAX_JSONL_LINE_BYTES" in source
    assert "MAX_MANIFEST_RECORDS" in source
    assert "MAX_TRAINING_EXAMPLES" in source
    assert "MAX_TRAINING_LABEL_POINTS" in source
    assert '"training_limits": training_limits' in source
    assert 'p.suffix.casefold() == ".jsonl"' in source
    assert "from scripts.voicebank_audit_summary import build_audit_index" in source
    assert "voicebank_audit_summary.json" in source
    assert "audit_index[\"aggregate\"]" in source
    assert 'json.dumps(download_summary, ensure_ascii=False, indent=2) + "\\\\n",' not in source


def test_safe_command_diagnostic_keeps_codes_without_private_payload():
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    source = "".join(
        "".join(cell["source"]) for cell in notebook["cells"]
        if cell.get("cell_type") == "code"
    )
    tree = ast.parse(source)
    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "safe_command_diagnostic"
    )
    isolated = ast.Module(body=[function], type_ignores=[])
    namespace = {"json": json, "re": re}
    exec(compile(isolated, str(NOTEBOOK), "exec"), namespace)
    diagnose = namespace["safe_command_diagnostic"]

    output = (
        "download starting\n"
        + json.dumps({
            "status": "failed",
            "error_code": "selected_file_count_limit_exceeded",
            "path": "/kaggle/temp/private/voicebank.zip",
            "alias": "SECRET_ALIAS",
        })
    )
    assert diagnose(output) == {
        "status": "failed",
        "error_code": "selected_file_count_limit_exceeded",
    }
    assert diagnose(json.dumps({
        "status": "private/path",
        "error_code": "private/error",
    })) == {}
    assert diagnose("not json") == {}
