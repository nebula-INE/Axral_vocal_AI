from __future__ import annotations

from pathlib import Path
import stat
import tarfile
import zipfile
from types import SimpleNamespace

import pytest

from scripts.audit_hf_voicebanks import (
    AuditFailure,
    HubFile,
    _safe_member_path,
    discover_voicebank_roots,
    enforce_download_limit,
    is_relevant_voicebank_file,
    safe_extract_archive,
    select_relevant_files,
    summarize_analysis,
)


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
        "banks/raw/PREFIX.MAP", "banks/raw/a.WAV", "banks/raw/oto.ini", "banks/voice.zip"
    ]
    assert sum(item.size for item in selected) == 3192


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
    with pytest.raises(AuditFailure, match="archive_link_rejected"):
        safe_extract_archive(archive, tmp_path / "out", 1024)


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
