from __future__ import annotations

import io
import hashlib
from pathlib import Path
import stat
import sys
import tarfile
from types import SimpleNamespace
import zipfile

import pytest

from scripts.kaggle_hf_download import (
    DownloadAuditError,
    HubFile,
    discover_voicebank_roots,
    download_dataset,
    enforce_download_limit,
    parse_dataset_url,
    safe_extract_archive,
    select_relevant_files,
)


def test_parse_dataset_url_accepts_repo_and_tree_revision():
    assert parse_dataset_url("https://huggingface.co/datasets/SEKOIA2900/VO-US") == (
        "SEKOIA2900/VO-US", "main"
    )
    assert parse_dataset_url(
        "https://huggingface.co/datasets/owner/repo/tree/feature-branch"
    ) == ("owner/repo", "feature-branch")


@pytest.mark.parametrize("url", [
    "http://huggingface.co/datasets/owner/repo",
    "https://evil.example/datasets/owner/repo",
    "https://huggingface.co/models/owner/repo",
    "https://huggingface.co/datasets/owner",
    "https://user:pass@huggingface.co/datasets/owner/repo",
])
def test_parse_dataset_url_rejects_non_dataset_or_unsafe_urls(url):
    with pytest.raises(DownloadAuditError):
        parse_dataset_url(url)


def test_select_relevant_files_includes_utau_files_and_jsonl_but_skips_directories():
    entries = [
        {"path": "banks/voice.zip", "size": 1000},
        {"path": "banks/raw/oto.ini", "size": 120},
        {"path": "banks/raw/prefix.map", "size": 24},
        {"path": "banks/raw/a.wav", "size": 2048},
        {"path": "labels/pitch_training_manifest.jsonl", "size": 512},
        {"path": "docs/README.md", "size": 20},
        {"path": "banks/Voice/LICENSE.txt", "size": 40},
        {"path": "banks/Voice/notes.JSONL", "size": 10},
        {"path": "banks/raw/", "size": None},
    ]
    selected = select_relevant_files(entries)
    assert {item.path for item in selected} == {
        "banks/voice.zip", "banks/raw/oto.ini", "banks/raw/prefix.map",
        "banks/raw/a.wav", "labels/pitch_training_manifest.jsonl", "docs/README.md",
        "banks/Voice/LICENSE.txt", "banks/Voice/notes.JSONL",
    }
    assert sum(item.size for item in selected) == 3774


def test_select_relevant_files_rejects_traversal():
    with pytest.raises(DownloadAuditError, match="unsafe_hub_path"):
        select_relevant_files([{"path": "../secret.zip", "size": 1}])


def test_download_limit_is_checked_before_transfer():
    with pytest.raises(DownloadAuditError, match="download_size_limit_exceeded"):
        enforce_download_limit([HubFile("a.zip", 6), HubFile("b.zip", 5)], 10)


def test_extract_zip_and_discover_nested_oto_files_as_one_bank(tmp_path):
    archive = tmp_path / "voice.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("Voice/oto.ini", "a.wav=a,0,0,0,0,0\n")
        bundle.writestr("Voice/nested/oto.ini", "i.wav=i,0,0,0,0,0\n")
        bundle.writestr("Voice/a.wav", b"RIFF")
    extracted = tmp_path / "out"
    safe_extract_archive(archive, extracted, 1024)
    assert discover_voicebank_roots(extracted) == [(extracted / "Voice").resolve()]


def test_extract_zip_preserves_utf8_and_ascii_member_names(tmp_path):
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


def test_extract_zip_repairs_legacy_cp932_member_names(tmp_path, monkeypatch):
    archive = tmp_path / "legacy-japanese.zip"

    # Older voicebank ZIPs often store CP932 path bytes without the UTF-8 flag.
    def encode_cp932(info):
        return info.filename.encode("cp932"), info.flag_bits & ~0x800

    monkeypatch.setattr(zipfile.ZipInfo, "_encodeFilenameFlags", encode_cp932)
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("音源/oto.ini", "あ.wav=あ,0,100,-100,20,10\n")

    destination = tmp_path / "legacy-extracted"
    safe_extract_archive(archive, destination, 1024)

    oto_path = destination / "音源" / "oto.ini"
    assert oto_path.is_file()
    assert oto_path.read_text(encoding="utf-8") == "あ.wav=あ,0,100,-100,20,10\n"


def test_extract_zip_rejects_traversal_and_removes_partial_destination(tmp_path):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../escape.txt", "bad")
    destination = tmp_path / "out"
    with pytest.raises(DownloadAuditError, match="unsafe_archive_member"):
        safe_extract_archive(archive, destination, 1024)
    assert not destination.exists()
    assert not (tmp_path.parent / "escape.txt").exists()


def test_extract_tar_rejects_symlink(tmp_path):
    archive = tmp_path / "link.tar"
    with tarfile.open(archive, "w") as bundle:
        info = tarfile.TarInfo("Voice/link")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        bundle.addfile(info)
    with pytest.raises(DownloadAuditError, match="archive_link_or_special_file_rejected"):
        safe_extract_archive(archive, tmp_path / "out", 1024)


def test_extract_zip_enforces_actual_extracted_byte_limit(tmp_path):
    archive = tmp_path / "voice.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("voice/large.wav", b"x" * 2048)
    with pytest.raises(DownloadAuditError, match="extracted_size_limit_exceeded"):
        safe_extract_archive(archive, tmp_path / "out", 1024)


def test_download_dataset_pins_revision_and_downloads_only_selected_files(tmp_path, monkeypatch):
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as bundle:
        bundle.writestr("Voice/oto.ini", "a.wav=a,0,0,0,0,0\n")
        bundle.writestr("Voice/a.wav", b"RIFF")
    archive_bytes = archive_buffer.getvalue()
    calls = {}

    class FakeApi:
        def __init__(self, token=None):
            calls["token"] = token

        def dataset_info(self, repo_id, revision):
            calls["dataset_info"] = (repo_id, revision)
            return SimpleNamespace(sha="abc123", cardData={"license": "cc-by-4.0"})

        def list_repo_tree(self, repo_id, repo_type, revision, recursive, expand):
            calls["list_repo_tree"] = (repo_id, repo_type, revision, recursive, expand)
            return [
                {"path": "voicebank.zip", "size": len(archive_bytes)},
                {"path": "README.md", "size": 50},
            ]

    def fake_snapshot_download(**kwargs):
        calls["snapshot_download"] = kwargs
        target = Path(kwargs["local_dir"]) / "voicebank.zip"
        target.write_bytes(archive_bytes)
        readme = Path(kwargs["local_dir"]) / "README.md"
        readme.write_text("---\nlicense: cc-by-4.0\n---\nDataset card", encoding="utf-8")
        return str(kwargs["local_dir"])

    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(HfApi=FakeApi, snapshot_download=fake_snapshot_download),
    )

    result = download_dataset(
        "https://huggingface.co/datasets/SEKOIA2900/VO-US/tree/main",
        tmp_path / "dataset",
        token="private-token",
        max_download_mb=1,
        max_extracted_mb=1,
    )

    assert calls["token"] == "private-token"
    assert calls["dataset_info"] == ("SEKOIA2900/VO-US", "main")
    assert calls["list_repo_tree"] == ("SEKOIA2900/VO-US", "dataset", "abc123", True, False)
    assert calls["snapshot_download"]["revision"] == "abc123"
    assert calls["snapshot_download"]["allow_patterns"] == ["README.md", "voicebank.zip"]
    assert result["resolved_revision"] == "abc123"
    assert result["dataset_card_license"] == "cc-by-4.0"
    assert result["voicebank_roots"] == 1
    assert result["license_documents"] == [{
        "source_root": "downloads",
        "path": "README.md",
        "size_bytes": 39,
        "sha256": hashlib.sha256(
            b"---\nlicense: cc-by-4.0\n---\nDataset card"
        ).hexdigest(),
    }]
    assert result["status"] == "completed"
    assert (tmp_path / "dataset" / "download_summary.json").is_file()


def test_extract_zip_rejects_symlink(tmp_path):
    archive = tmp_path / "link.zip"
    link = zipfile.ZipInfo("Voice/link")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(link, "../../outside")
    with pytest.raises(DownloadAuditError, match="archive_link_or_special_file_rejected"):
        safe_extract_archive(archive, tmp_path / "out", 1024)
    assert not (tmp_path / "out").exists()


def test_extract_zip_rejects_case_insensitive_duplicate_members(tmp_path):
    archive = tmp_path / "duplicate.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("Voice/oto.ini", "first")
        bundle.writestr("voice/OTO.INI", "second")
    with pytest.raises(DownloadAuditError, match="archive_duplicate_path"):
        safe_extract_archive(archive, tmp_path / "out", 1024)
    assert not (tmp_path / "out").exists()


def test_extract_tar_rejects_hardlink(tmp_path):
    archive = tmp_path / "hardlink.tar"
    with tarfile.open(archive, "w") as bundle:
        info = tarfile.TarInfo("Voice/hardlink")
        info.type = tarfile.LNKTYPE
        info.linkname = "Voice/oto.ini"
        bundle.addfile(info)
    with pytest.raises(DownloadAuditError, match="archive_link_or_special_file_rejected"):
        safe_extract_archive(archive, tmp_path / "out", 1024)
    assert not (tmp_path / "out").exists()


def test_download_summary_reports_archive_failures_with_paths(tmp_path, monkeypatch):
    class FakeApi:
        def __init__(self, token=None):
            pass

        def dataset_info(self, repo_id, revision):
            return SimpleNamespace(sha="abc123", cardData=None)

        def list_repo_tree(self, repo_id, repo_type, revision, recursive, expand):
            return [
                {"path": "banks/broken.zip", "size": 4},
                {"path": "loose/oto.ini", "size": 20},
            ]

    def fake_snapshot_download(**kwargs):
        root = Path(kwargs["local_dir"])
        archive = root / "banks" / "broken.zip"
        archive.parent.mkdir(parents=True)
        archive.write_bytes(b"nope")
        loose_oto = root / "loose" / "oto.ini"
        loose_oto.parent.mkdir(parents=True)
        loose_oto.write_text("a.wav=a,0,0,0,0,0\n", encoding="utf-8")
        return str(root)

    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(HfApi=FakeApi, snapshot_download=fake_snapshot_download),
    )

    summary = download_dataset(
        "https://huggingface.co/datasets/owner/repo",
        tmp_path / "dataset",
        max_download_mb=1,
        max_extracted_mb=1,
    )

    assert summary["status"] == "completed_with_archive_errors"
    assert summary["voicebank_roots"] == 1
    assert summary["archives_found"] == 1
    assert summary["archive_results"] == [{
        "path": "banks/broken.zip",
        "size_bytes": 4,
        "status": "failed",
        "error_code": "unsupported_or_invalid_archive",
        "extracted_bytes": 0,
    }]
    assert summary["archive_errors"] == ["unsupported_or_invalid_archive"]
    saved = __import__("json").loads(
        (tmp_path / "dataset" / "download_summary.json").read_text(encoding="utf-8")
    )
    assert saved["status"] == "completed_with_archive_errors"

