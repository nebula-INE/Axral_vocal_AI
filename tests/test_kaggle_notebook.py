"""Structural checks for the single-cell Kaggle notebook."""
import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "kaggle" / "Axral_Vocal_AI_OneCell.ipynb"


def test_kaggle_notebook_is_valid_json_and_has_one_executable_cell():
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    assert notebook["nbformat"] == 4
    code_cells = [cell for cell in notebook["cells"] if cell.get("cell_type") == "code"]
    assert len(code_cells) == 1
    source = "".join(code_cells[0]["source"])
    ast.parse(source)
    assert 'HF_DATA_URL = "https://huggingface.co/datasets/' in source
    assert "training/validate_dataset.py" in source
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
    assert "output_tail=0, redact_output=True" in source
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
    assert '"download": public_download_summary' in source
    assert '"manifest_index": manifest_index' in source
    assert "artifact_files = [" in source
    assert 'OUT / "voicebank_audit_summary.json"' in source
    assert 'OUT / "models" / "pitch_delta_report.json"' in source
    assert 'for artifact in OUT.rglob("*")' not in source
    assert 'OUT / "audits"' not in source
    assert source.index("TEMP_DATA_CLEANED") < source.index("with zipfile.ZipFile(archive")
    assert "sys.path.insert(0, str(PROJECT))" in source
    assert "audit_results = []" in source
    assert "blocked_voicebank_audit_findings" in source
    assert '"audit_failures": audit_failures' in source
    assert '(OUT / "download_summary.json").write_text' in source
    assert "license/readme documents indexed" in source
    assert '["git", "status", "--porcelain"]' in source
    assert '["git", "fetch", "--depth", "1", "origin", "main"]' in source
    assert "required_pipeline_files" in source
    assert '["git", "fetch", "--depth", "1", "origin", "feat/kaggle-one-url-pipeline"]' in source
    assert "Default branch does not contain the Kaggle pipeline helpers yet" in source
    assert "Axral checkout is missing required Kaggle pipeline files" in source
    assert '["git", "reset", "--hard", "FETCH_HEAD"]' in source
    assert "local changes" in source
    assert "source_commit" in source
    assert 'p.suffix.casefold() == ".jsonl"' in source
    assert "from scripts.voicebank_audit_summary import build_audit_index" in source
    assert "voicebank_audit_summary.json" in source
    assert "audit_index[\"aggregate\"]" in source
    assert 'json.dumps(download_summary, ensure_ascii=False, indent=2) + "\\\\n",' not in source
