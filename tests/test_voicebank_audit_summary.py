from __future__ import annotations

import json
from pathlib import Path

from scripts.voicebank_audit_summary import build_audit_index, build_public_download_summary


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
        "error_code": "audit_cli_nonzero_exit",
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
        "error_code": "invalid_or_missing_audit_report",
    }]


def test_build_audit_index_ignores_bool_and_negative_counters(tmp_path):
    report = tmp_path / "audit.json"
    report.write_text(json.dumps({
        "summary": {
            "errors": 0,
            "warnings": 0,
            "unexpected": True,
            "negative": -1,
            "valid": 3,
        },
    }), encoding="utf-8")
    result = build_audit_index([(1, report, 0)])
    assert result["aggregate"] == {"errors": 0, "warnings": 0, "valid": 3}



def test_missing_report_blocks_training_even_when_cli_returns_zero(tmp_path):
    missing = tmp_path / "missing.json"

    result = build_audit_index([(3, missing, 0)])

    assert result["audits_completed"] == 0
    assert result["failures"] == [{
        "bank_index": 3,
        "exit_code": 0,
        "error_count": 0,
        "error_code": "invalid_or_missing_audit_report",
    }]
    assert result["banks"][0]["status"] == "invalid_or_missing_report"


def test_report_errors_block_training_even_when_cli_returns_zero(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({
        "summary": {"errors": 2, "warnings": 0, "oto_entries": 8}
    }), encoding="utf-8")

    result = build_audit_index([(4, report, 0)])

    assert result["audits_completed"] == 1
    assert result["aggregate"]["errors"] == 2
    assert result["failures"] == [{
        "bank_index": 4,
        "exit_code": 0,
        "error_count": 2,
        "error_code": "audit_report_contains_errors",
    }]
    assert result["banks"][0]["status"] == "completed_with_findings"


def test_required_audit_counters_must_be_present_and_valid(tmp_path):
    report = tmp_path / "malformed.json"
    report.write_text(json.dumps({"summary": {"errors": False, "warnings": 0}}),
                      encoding="utf-8")

    result = build_audit_index([(5, report, 0)])

    assert result["audits_completed"] == 0
    assert result["aggregate"] == {}
    assert result["failures"][0]["error_code"] == "invalid_or_missing_audit_report"
    assert result["banks"][0]["status"] == "invalid_or_missing_report"



def test_public_download_summary_omits_archive_and_license_document_paths():
    private_summary = {
        "dataset": "SEKOIA2900/VO-US",
        "requested_revision": "main",
        "resolved_revision": "abc123",
        "dataset_card_license": "other",
        "license_documents": [
            {"path": "secret_voicebank/README.md", "sha256": "abc"},
            {"path": "secret_voicebank/LICENSE.txt", "sha256": "def"},
        ],
        "selected_files": 12,
        "download_bytes": 1024,
        "archives_found": 2,
        "archive_results": [
            {"path": "private/音源.zip", "status": "extracted", "error_code": None},
            {"path": "private/another.zip", "status": "failed",
             "error_code": "archive_duplicate_path"},
        ],
        "archive_errors": ["archive_duplicate_path"],
        "extracted_bytes": 2048,
        "voicebank_roots": 3,
        "status": "completed_with_archive_errors",
    }

    public = build_public_download_summary(private_summary)

    assert public == {
        "schema_version": 1,
        "dataset": "SEKOIA2900/VO-US",
        "requested_revision": "main",
        "resolved_revision": "abc123",
        "dataset_card_license": "other",
        "license_documents_indexed": 2,
        "selected_files": 12,
        "download_bytes": 1024,
        "archives_found": 2,
        "archive_status_counts": {"extracted": 1, "failed": 1},
        "archive_error_code_counts": {"archive_duplicate_path": 1},
        "extracted_bytes": 2048,
        "voicebank_roots": 3,
        "status": "completed_with_archive_errors",
    }
    rendered = json.dumps(public, ensure_ascii=False)
    assert "private/" not in rendered
    assert "secret_voicebank" not in rendered
    assert "音源.zip" not in rendered
