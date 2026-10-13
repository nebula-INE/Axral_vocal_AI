import json
import subprocess
import sys
from pathlib import Path


def test_dataset_audit_cli_includes_label_quality_review(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    manifest = tmp_path / "manifest.jsonl"
    report_path = tmp_path / "readiness.json"
    row = {
        "schema_version": 1,
        "record_id": "cli-smoke-1",
        "source_id": "cli-smoke-source-1",
        "permission_status": "approved",
        "license_id": "INTERNAL-ML-PERMISSION-001",
        "voicebank_id": "fixture-bank",
        "split": "train",
        "input": {
            "notes": [
                {
                    "start_sec": 0.0,
                    "end_sec": 1.0,
                    "midi_note": 60,
                    "lyric": "a",
                    "voiced": True,
                }
            ]
        },
        "target": {
            "kind": "pitch_delta_semitones",
            "points": [
                {"time_sec": 0.2, "delta_semitones": 0.0},
                {"time_sec": 0.3, "delta_semitones": 1.5},
            ],
            "label_source": "synthetic_fixture",
            "confidence": 1.0,
        },
        "provenance": {
            "acquisition_method": "curated fixture",
            "source_reference": "synthetic://fixture",
            "review_date": "2026-10-13",
            "review_status": "approved",
        },
        "preprocessing": {
            "tool_version": "fixture-1",
            "transformations": [],
        },
    }
    manifest.write_text(json.dumps(row) + "\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "training" / "audit_pitch_dataset.py"),
            str(manifest),
            "--output",
            str(report_path),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    saved_report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["manifest_validation"]["status"] == "valid"
    assert report["label_quality_review"]["labels_seen"] == 2
    assert report["label_quality_review"]["records_with_flags"] == 1
    assert saved_report["label_quality_review"] == report["label_quality_review"]
