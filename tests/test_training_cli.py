import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "training" / "train_pitch_model.py"


def _record(record_id: str, bank: str, split: str, delta: float) -> dict:
    return {
        "schema_version": 1,
        "record_id": record_id,
        "source_id": f"synthetic-{record_id}",
        "permission_status": "approved",
        "license_id": "SYNTHETIC-TEST-ONLY",
        "voicebank_id": bank,
        "split": split,
        "input": {
            "notes": [
                {
                    "start_sec": 0.0,
                    "end_sec": 1.0,
                    "midi_note": 60,
                    "lyric": "synthetic",
                    "voiced": True,
                }
            ]
        },
        "target": {
            "kind": "pitch_delta_semitones",
            "points": [{"time_sec": 0.2, "delta_semitones": delta}],
            "label_source": "synthetic_fixture",
            "confidence": 1.0,
        },
        "provenance": {
            "acquisition_method": "synthetic",
            "source_reference": "synthetic://fixture",
            "review_date": "2026-10-11",
            "review_status": "approved",
        },
        "preprocessing": {"tool_version": "test-1", "transformations": []},
    }


def _manifest(tmp_path: Path) -> Path:
    path = tmp_path / "manifest.jsonl"
    records = [
        _record("train", "bank-train", "train", 0.2),
        _record("validation", "bank-validation", "validation", 0.3),
        _record("test", "bank-test", "test", 0.4),
    ]
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in records),
        encoding="utf-8",
    )
    return path


def test_training_cli_omits_held_out_test_metrics_by_default(tmp_path):
    manifest = _manifest(tmp_path)
    output = tmp_path / "report.json"

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(manifest), "--output", str(output)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["test_evaluation_included"] is False
    assert set(report["evaluation_by_split"]) == {"train", "validation"}
    assert "test" not in report["mae_semitones"]


def test_training_cli_evaluates_test_only_with_explicit_opt_in(tmp_path):
    manifest = _manifest(tmp_path)
    output = tmp_path / "report.json"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(manifest),
            "--output",
            str(output),
            "--evaluate-test",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["test_evaluation_included"] is True
    assert set(report["evaluation_by_split"]) == {"train", "validation", "test"}
    assert "test" in report["mae_semitones"]
