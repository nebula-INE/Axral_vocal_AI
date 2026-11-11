from __future__ import annotations

import io
from pathlib import Path
import stat
import sys
import tarfile
import zipfile
from types import SimpleNamespace

import pytest

import scripts.audit_hf_voicebanks as audit_script
from scripts.audit_hf_voicebanks import (
    build_markdown,
    run_audit,
    AuditFailure,
    HubFile,
    _safe_member_path,
    discover_voicebank_roots,
    enforce_download_limit,
    is_relevant_voicebank_file,
    safe_extract_archive,
    select_relevant_files,
    summarize_analysis,
    _validate_repo_id,
    _validate_requested_revision,
)


@pytest.mark.parametrize("revision", ["main", "release/2026.11", "feature/voicebank-audit"])
def test_requested_hub_revision_accepts_safe_refs(revision):
    assert _validate_requested_revision(revision) == revision


@pytest.mark.parametrize("revision", [
    "", "../main", "refs/../main", "feature\n# injected markdown",
    "release|[link](https://example.invalid)", "a" * 129, ".hidden", "feature//branch",
])
def test_requested_hub_revision_rejects_unsafe_values(revision):
    with pytest.raises(AuditFailure, match="invalid_requested_revision"):
        _validate_requested_revision(revision)


@pytest.mark.parametrize("repo_id", [
    "SEKOIA2900/VO-US", "owner/repo-name", "owner/repo_name"
])
def test_hub_repo_id_accepts_safe_identifiers(repo_id):
    assert _validate_repo_id(repo_id) == repo_id


@pytest.mark.parametrize("repo_id", [
    "../private/repo", "owner/repo\n# injected", "owner/repo|[link](x)", "owner"
])
def test_hub_repo_id_rejects_unsafe_values(repo_id):
    with pytest.raises(AuditFailure, match="invalid_dataset_repo_id"):
        _validate_repo_id(repo_id)


def test_run_audit_rejects_markdown_injection_revision_before_hub_request(tmp_path, monkeypatch):
    calls = []

    class FakeHfApi:
        def __init__(self, token=None):
            calls.append("client_created")

        def dataset_info(self, repo_id, revision):
            calls.append("dataset_info")
            raise AssertionError("invalid revision must be rejected before Hub API calls")

    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(HfApi=FakeHfApi, snapshot_download=lambda **kwargs: calls.append("download")),
    )
    malicious = "feature\n# injected markdown"
    args = SimpleNamespace(
        repo_id="SEKOIA2900/VO-US",
        revision=malicious,
        file_path_filter="",
        voicebank_filter="",
        max_download_mb=10,
        max_extracted_mb=10,
        fail_on="error",
        output_dir=tmp_path / "summary",
    )

    summary, exit_code = run_audit(args)

    assert exit_code == 2
    assert summary["status"] == "failed"
    assert summary["fatal_error_code"] == "invalid_requested_revision"
    assert summary["requested_revision"] is None
    assert calls == []
    markdown = build_markdown(summary)
    assert "injected markdown" not in markdown


def test_file_selection_keeps_archives_utau_metadata_and_wav_only():
    rows = [
        {"path": "banks/voice.zip", "size": 1000},
        {"path": "banks/raw/oto.ini", "size": 120},
        {"path": "banks/raw/PREFIX.MAP", "size": 24},
        {"path": "banks/raw/a.WAV", "size": 2048},
        {"path": "docs/README.md", "size": 20},
        {"path": "cache/sample.frq", "size": 300},
    ]
    selected = select_relevant_files(rows)
    assert [item.path for item in selected] == [
        "banks/raw/a.WAV", "banks/raw/oto.ini", "banks/raw/PREFIX.MAP", "banks/voice.zip"
    ]
    assert sum(item.size for item in selected) == 3192


def test_file_path_filter_is_applied_before_download_selection():
    rows = [
        {"path": "banks/tsukuyomi/voice.zip", "size": 100},
        {"path": "banks/other/voice.zip", "size": 200},
        {"path": "banks/tsukuyomi/oto.ini", "size": 10},
    ]
    selected = select_relevant_files(rows, path_filter="tsukuyomi")
    assert [item.path for item in selected] == [
        "banks/tsukuyomi/oto.ini", "banks/tsukuyomi/voice.zip"
    ]


@pytest.mark.parametrize("path", ["../escape.wav", "/absolute.wav", "C:\\escape.wav", ""])
def test_selection_rejects_unsafe_hub_paths(path):
    with pytest.raises(AuditFailure):
        is_relevant_voicebank_file(path)


def test_unknown_relevant_file_size_is_rejected():
    with pytest.raises(AuditFailure, match="hub_file_size_unavailable"):
        select_relevant_files([{"path": "bank/oto.ini"}])


def test_download_limit_fails_before_download():
    with pytest.raises(AuditFailure, match="download_size_limit_exceeded"):
        enforce_download_limit([HubFile("bank.zip", 1024)], 100)


def test_safe_archive_member_rejects_parent_and_absolute_paths():
    for value in ("../escape.wav", "/tmp/escape.wav", "C:\\Windows\\a.wav", "\\\\server\\share\\a.wav"):
        with pytest.raises(AuditFailure):
            _safe_member_path(value)


def test_zip_extracts_files_under_destination(tmp_path):
    archive = tmp_path / "voice.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("voice/oto.ini", "a.wav=あ,0,100,-100,20,10")
        bundle.writestr("voice/a.wav", b"RIFF-test")
    destination = tmp_path / "out"
    written = safe_extract_archive(archive, destination, 1024)
    assert written == len("a.wav=あ,0,100,-100,20,10".encode()) + len(b"RIFF-test")
    assert (destination / "voice" / "oto.ini").is_file()
    assert (destination / "voice" / "a.wav").read_bytes() == b"RIFF-test"


def test_zip_extraction_preserves_utf8_and_ascii_member_names(tmp_path):
    archive = tmp_path / "ordinary-names.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("plain/readme.txt", "ASCII name")
        bundle.writestr("日本語音源/あ.wav", b"RIFF-utf8-name")

    with zipfile.ZipFile(archive) as bundle:
        members = {info.filename: info.flag_bits for info in bundle.infolist()}
    assert not (members["plain/readme.txt"] & 0x800)
    assert members["日本語音源/あ.wav"] & 0x800

    destination = tmp_path / "ordinary-out"
    safe_extract_archive(archive, destination, 1024)

    assert (destination / "plain" / "readme.txt").read_text(encoding="utf-8") == "ASCII name"
    assert (destination / "日本語音源" / "あ.wav").read_bytes() == b"RIFF-utf8-name"


def test_zip_extraction_repairs_legacy_cp932_member_names(tmp_path, monkeypatch):
    archive = tmp_path / "legacy-japanese.zip"

    # Older Japanese voicebank ZIPs may omit the UTF-8 flag on CP932 names.
    def encode_cp932(info):
        return info.filename.encode("cp932"), info.flag_bits & ~0x800

    monkeypatch.setattr(zipfile.ZipInfo, "_encodeFilenameFlags", encode_cp932)
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("音源/oto.ini", "あ.wav=あ,0,100,-100,20,10\n")
        bundle.writestr("音源/あ.wav", b"RIFF-japanese-name")

    destination = tmp_path / "legacy-out"
    safe_extract_archive(archive, destination, 1024)

    assert (destination / "音源" / "oto.ini").is_file()
    assert (destination / "音源" / "あ.wav").read_bytes() == b"RIFF-japanese-name"


def test_zip_extraction_rejects_special_files(tmp_path):
    archive = tmp_path / "device.zip"
    info = zipfile.ZipInfo("voice/device.wav")
    info.create_system = 3
    info.external_attr = (stat.S_IFCHR | 0o600) << 16
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(info, b"device")

    with pytest.raises(AuditFailure, match="archive_link_or_special_file_rejected"):
        safe_extract_archive(archive, tmp_path / "device-out", 1024)


def test_zip_extraction_rejects_path_traversal_and_cleans_partial_output(tmp_path):
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("safe/first.txt", "first")
        bundle.writestr("../outside.txt", "escape")
    destination = tmp_path / "out"
    with pytest.raises(AuditFailure, match="unsafe_archive_member"):
        safe_extract_archive(archive, destination, 1024)
    assert not destination.exists()
    assert not (tmp_path / "outside.txt").exists()


def test_zip_extraction_rejects_symlinks(tmp_path):
    archive = tmp_path / "link.zip"
    info = zipfile.ZipInfo("voice/link.wav")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(info, "../../outside.wav")
    with pytest.raises(AuditFailure, match="archive_link_or_special_file_rejected"):
        safe_extract_archive(archive, tmp_path / "out", 1024)


def test_tar_extraction_accepts_common_dot_root_directory_entry(tmp_path):
    archive = tmp_path / "voice.tar"
    with tarfile.open(archive, "w") as bundle:
        root_entry = tarfile.TarInfo("./")
        root_entry.type = tarfile.DIRTYPE
        bundle.addfile(root_entry)
        contents = b"sample.wav=\xe3\x81\x82,0,100,-100,20,10"
        member = tarfile.TarInfo("./voice/oto.ini")
        member.size = len(contents)
        bundle.addfile(member, io.BytesIO(contents))
    destination = tmp_path / "out"
    written = safe_extract_archive(archive, destination, 1024)
    assert written == len(contents)
    assert (destination / "voice" / "oto.ini").read_bytes() == contents


def test_tar_extraction_rejects_links(tmp_path):
    archive = tmp_path / "link.tar"
    with tarfile.open(archive, "w") as bundle:
        member = tarfile.TarInfo("voice/link.wav")
        member.type = tarfile.SYMTYPE
        member.linkname = "../../outside.wav"
        bundle.addfile(member)
    with pytest.raises(AuditFailure, match="archive_link_or_special_file_rejected"):
        safe_extract_archive(archive, tmp_path / "out", 1024)


def test_archive_extraction_enforces_uncompressed_size_limit(tmp_path):
    archive = tmp_path / "large.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("voice/a.wav", b"x" * 200)
    with pytest.raises(AuditFailure, match="extracted_size_limit_exceeded"):
        safe_extract_archive(archive, tmp_path / "out", 100)


def test_voicebank_discovery_groups_nested_oto_ini_under_top_bank(tmp_path):
    bank_a = tmp_path / "bank-a"
    nested = bank_a / "append"
    bank_b = tmp_path / "bank-b"
    nested.mkdir(parents=True)
    bank_b.mkdir()
    (bank_a / "oto.ini").write_text("", encoding="utf-8")
    (nested / "oto.ini").write_text("", encoding="utf-8")
    (bank_b / "OTO.INI").write_text("", encoding="utf-8")
    assert discover_voicebank_roots(tmp_path) == [bank_a.resolve(), bank_b.resolve()]


def test_voicebank_discovery_ignores_symlinked_directories(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "oto.ini").write_text("", encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    try:
        (root / "external").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    assert discover_voicebank_roots(root) == []


def test_public_summary_contains_counts_only_not_sensitive_names():
    fake = SimpleNamespace(
        summary={
            "oto_files": 1, "oto_entries": 4, "unique_aliases": 4,
            "prefix_map_files": 1, "prefix_map_entries": 2,
            "wav_files_checked": 4, "wav_files_invalid": 0,
            "errors": 0, "warnings": 1,
        },
        issues=[
            SimpleNamespace(severity="warning", code="duplicate_alias",
                            alias="SECRET_ALIAS", path="private.wav")
        ],
    )
    report = summarize_analysis(1, fake)
    serialized = str(report)
    assert report["bank_index"] == 1
    assert report["counts"]["oto_entries"] == 4
    assert "warning:duplicate_alias" in serialized
    assert "SECRET_ALIAS" not in serialized
    assert "private.wav" not in serialized
    assert "oto.ini" not in serialized



def test_run_audit_reports_archive_error_codes_without_archive_paths(tmp_path, monkeypatch):
    class FakeHfApi:
        def __init__(self, token=None):
            self.token = token

        def dataset_info(self, repo_id, revision):
            return SimpleNamespace(sha="a" * 40)

        def list_repo_tree(self, repo_id, repo_type, revision, recursive, expand):
            return [
                {"path": "banks/broken.zip", "size": 8},
                {"path": "banks/voice/oto.ini", "size": 20},
            ]

    def fake_snapshot_download(repo_id, repo_type, revision, local_dir,
                               allow_patterns, token):
        root = Path(local_dir)
        (root / "banks" / "voice").mkdir(parents=True)
        (root / "banks" / "broken.zip").write_bytes(b"not-a-zip")
        (root / "banks" / "voice" / "oto.ini").write_text(
            "a.wav=あ,0,100,-100,20,10\n", encoding="utf-8"
        )

    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(HfApi=FakeHfApi, snapshot_download=fake_snapshot_download),
    )
    monkeypatch.setattr(
        audit_script,
        "safe_extract_archive",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AuditFailure("archive_duplicate_path")
        ),
    )
    monkeypatch.setattr(
        audit_script,
        "analyze_voicebank",
        lambda root: SimpleNamespace(
            summary={
                "oto_files": 1, "oto_entries": 1, "unique_aliases": 1,
                "prefix_map_files": 0, "prefix_map_entries": 0,
                "wav_files_checked": 0, "wav_files_invalid": 0,
                "errors": 0, "warnings": 0,
            },
            issues=[],
        ),
    )

    args = SimpleNamespace(
        repo_id="SEKOIA2900/VO-US",
        revision="main",
        file_path_filter="",
        voicebank_filter="",
        max_download_mb=10,
        max_extracted_mb=10,
        fail_on="error",
        output_dir=tmp_path / "summary",
    )
    summary, exit_code = run_audit(args)

    assert exit_code == 1
    assert summary["archive_errors"] == 1
    assert summary["archive_error_codes"] == {"archive_duplicate_path": 1}
    assert summary["totals"]["errors"] == 1
    markdown = build_markdown(summary)
    assert "archive_duplicate_path" in markdown
    assert "broken.zip" not in markdown
    assert "banks/voice" not in markdown


def test_run_audit_rejects_non_commit_revision_before_listing_or_download(tmp_path, monkeypatch):
    calls = []

    class FakeHfApi:
        def __init__(self, token=None):
            pass

        def dataset_info(self, repo_id, revision):
            return SimpleNamespace(sha="not-a-commit-sha")

        def list_repo_tree(self, *args, **kwargs):
            calls.append("list_repo_tree")
            return []

    def fake_snapshot_download(**kwargs):
        calls.append("snapshot_download")

    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(HfApi=FakeHfApi, snapshot_download=fake_snapshot_download),
    )
    args = SimpleNamespace(
        repo_id="SEKOIA2900/VO-US",
        revision="main",
        file_path_filter="",
        voicebank_filter="",
        max_download_mb=10,
        max_extracted_mb=10,
        fail_on="error",
        output_dir=tmp_path / "summary",
    )

    summary, exit_code = run_audit(args)

    assert exit_code == 2
    assert summary["status"] == "failed"
    assert summary["fatal_error_code"] == "dataset_revision_unresolved"
    assert calls == []
