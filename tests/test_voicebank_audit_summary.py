from __future__ import annotations

import json
from pathlib import Path

from scripts.voicebank_audit_summary import build_audit_index


def test_build_audit_index_aggregates_counts_and_redacts_file_paths(tmp_path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text(json.dumps({
        "root": "/private/voicebank-a",
        "entries": [{"alias": "sensitive alias"}],
        "summary": {
            "oto_files": 2,
            "oto_entries": 20,
            "wav_files_checked": 18,
            "errors": 1,
            "warnings": 3,
        },
    }), encoding="utf-8")
    second.write_text(json.dumps({
        "root": "/private/voicebank-b",
        "summary": {
            "oto_files": 1,
            "oto_entries": 5,
            "wav_files_checked": 4,
            "errors": 0,
            "warnings": 2,
        },
    }), encoding="utf-8")

    result = build_audit_index([
        (1, first, 1),
        (2, second, 0),
    ])

    assert result["schema_version"] == 1
    assert result["voicebank_roots"] == 2
    assert result["audits_completed"] == 2
    assert result["aggregate"] == {
        "errors": 1,
        "oto_entries": 25,
        "oto_files": 3,
        "warnings": 5,
        "wav_files_checked": 22,
    }
    assert result["failures"] == [{
        "bank_index": 1,
        "exit_code": 1,
        "error_count": 1,
    }]
    assert result["banks"][0]["status"] == "completed_with_findings"
    rendered = json.dumps(result)
    assert "/private/" not in rendered
    assert "sensitive alias" not in rendered
    assert str(first) not in rendered


def test_build_audit_index_records_invalid_or_missing_report(tmp_path):
    missing = tmp_path / "missing.json"
    result = build_audit_index([(7, missing, 2)])
    assert result["voicebank_roots"] == 1
    assert result["audits_completed"] == 0
    assert result["aggregate"] == {}
    assert result["banks"] == [{
        "bank_index": 7,
        "status": "invalid_or_missing_report",
        "summary": {},
    }]
    assert result["failures"] == [{
        "bank_index": 7,
        "exit_code": 2,
        "error_count": 0,
    }]


def test_build_audit_index_ignores_bool_and_negative_counters(tmp_path):
    report = tmp_path / "audit.json"
    report.write_text(json.dumps({
        "summary": {
            "errors": 0,
            "unexpected": True,
            "negative": -1,
            "valid": 3,
        },
    }), encoding="utf-8")
    result = build_audit_index([(1, report, 0)])
    assert result["aggregate"] == {"errors": 0, "valid": 3}
