from __future__ import annotations

import io
from pathlib import Path
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
        {"path": "banks/raw/", "size": None},
    ]
    selected = select_relevant_files(entries)
    assert {item.path for item in selected} == {
        "banks/voice.zip", "banks/raw/oto.ini", "banks/raw/prefix.map",
        "banks/raw/a.wav", "labels/pitch_training_manifest.jsonl",
    }
    assert sum(item.size for item in selected) == 3704


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
            return SimpleNamespace(sha="abc123")

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
    assert calls["snapshot_download"]["allow_patterns"] == ["voicebank.zip"]
    assert result["resolved_revision"] == "abc123"
    assert result["voicebank_roots"] == 1
    assert result["status"] == "completed"
    assert (tmp_path / "dataset" / "download_summary.json").is_file()
