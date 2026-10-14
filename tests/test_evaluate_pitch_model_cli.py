import json
import subprocess
import sys
from pathlib import Path


def _manifest_row(split, target_deltas):
    return {
        "schema_version": 1,
        "record_id": f"eval-{split}",
        "source_id": f"eval-source-{split}",
        "permission_status": "approved",
        "license_id": "INTERNAL-ML-PERMISSION-001",
        "voicebank_id": f"eval-bank-{split}",
        "split": split,
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
                {"time_sec": 0.2 + index * 0.1, "delta_semitones": delta}
                for index, delta in enumerate(target_deltas)
            ],
            "label_source": "synthetic_fixture",
            "confidence": 1.0,
        },
        "provenance": {
            "acquisition_method": "curated fixture",
            "source_reference": f"synthetic://evaluation/{split}",
            "review_date": "2026-10-14",
            "review_status": "approved",
        },
        "preprocessing": {
            "tool_version": "fixture-1",
            "transformations": [],
        },
    }


def test_evaluation_cli_scopes_label_review_to_requested_split(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    manifest = tmp_path / "manifest.jsonl"
    model_path = tmp_path / "model.json"
    report_path = tmp_path / "validation.json"
    rows = [
        _manifest_row("train", [0.0]),
        _manifest_row("validation", [0.0, 1.5]),
        _manifest_row("test", [-1.5, -1.0, -0.5]),
    ]
    manifest.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    model_path.write_text(
        json.dumps({
            "model_type": "linear_ridge_pitch_delta",
            "schema_version": 1,
            "feature_version": 1,
            "feature_names": [
                "bias", "midi_normalized", "note_phase",
                "phase_squared", "duration_seconds",
            ],
            "target_kind": "pitch_delta_semitones",
            "weights": [0.25, 0.0, 0.0, 0.0, 0.0],
            "safety": {
                "proposal_only": True,
                "waveform_generation": False,
                "production_renderer_integration": False,
            },
        }),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "training" / "evaluate_pitch_model.py"),
            str(manifest),
            str(model_path),
            "--split", "validation",
            "--output", str(report_path),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    saved_report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["split"] == "validation"
    assert report["evaluation_scope"] == {
        "split": "validation",
        "records_in_split": 1,
        "usable_labeled_examples": 2,
        "held_out_test_metrics_included": False,
    }
    assert report["label_quality_review"]["labels_seen"] == 2
    assert report["label_quality_review"]["records_with_flags"] == 1
    assert "eval-bank-test" not in report["by_voicebank"]
    assert saved_report["label_quality_review"] == report["label_quality_review"]
