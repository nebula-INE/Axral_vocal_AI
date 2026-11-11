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
    assert "sys.path.insert(0, str(PROJECT))" in source
    assert "audit_failures = []" in source
    assert "blocked_voicebank_audit_findings" in source
    assert '"audit_failures": audit_failures' in source
    assert '(OUT / "download_summary.json").write_text' in source
    assert "license/readme documents indexed" in source
    assert "git status --porcelain" in source
    assert "git fetch" in source
    assert "git reset --hard FETCH_HEAD" in source
    assert "local changes" in source
    assert "source_commit" in source
