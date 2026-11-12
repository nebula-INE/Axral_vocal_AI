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

import scripts.kaggle_hf_download as kaggle_download
from scripts.kaggle_hf_download import (
    DownloadAuditError,
    HubFile,
    discover_voicebank_roots,
    collect_archive_paths,
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
    assert parse_dataset_url(
        "https://huggingface.co/datasets/owner/repo/tree/feature%2Fbranch"
    ) == ("owner/repo", "feature/branch")


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


def test_download_and_extraction_limits_cannot_exceed_hard_caps(tmp_path):
    with pytest.raises(DownloadAuditError, match="download_limit_out_of_range"):
        kaggle_download.download_dataset(
            "https://huggingface.co/datasets/owner/repo",
            tmp_path / "download-too-large",
            max_download_mb=kaggle_download.MAX_DOWNLOAD_MB + 1,
        )
    with pytest.raises(DownloadAuditError, match="extraction_limit_out_of_range"):
        kaggle_download.download_dataset(
            "https://huggingface.co/datasets/owner/repo",
            tmp_path / "extract-too-large",
            max_extracted_mb=kaggle_download.MAX_EXTRACTED_MB + 1,
        )
    with pytest.raises(DownloadAuditError, match="download_limit_out_of_range"):
        enforce_download_limit(
            [HubFile("voice.zip", 1)],
            (kaggle_download.MAX_DOWNLOAD_MB + 1) * 1024 * 1024,
        )


def test_hub_file_paths_have_individual_and_aggregate_byte_limits(monkeypatch):
    monkeypatch.setattr(kaggle_download, "MAX_HUB_PATH_BYTES", 8)
    with pytest.raises(DownloadAuditError, match="hub_path_length_limit_exceeded"):
        select_relevant_files([{"path": "bank/oto.ini", "size": 1}])

    monkeypatch.setattr(kaggle_download, "MAX_HUB_PATH_BYTES", 128)
    monkeypatch.setattr(kaggle_download, "MAX_SELECTED_PATH_BYTES", 15)
    with pytest.raises(DownloadAuditError, match="selected_path_bytes_limit_exceeded"):
        select_relevant_files([
            {"path": "a/oto.ini", "size": 1},
            {"path": "b/oto.ini", "size": 1},
        ])


@pytest.mark.parametrize("archive_kind", ("zip", "tar"))
def test_archive_path_metadata_has_aggregate_byte_limit(
    tmp_path, monkeypatch, archive_kind
):
    monkeypatch.setattr(kaggle_download, "MAX_TOTAL_ARCHIVE_PATH_BYTES", 5)
    archive = tmp_path / f"many-paths.{archive_kind}"
    if archive_kind == "zip":
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("aaa", b"a")
            bundle.writestr("bbb", b"b")
    else:
        with tarfile.open(archive, "w") as bundle:
            for name, payload in (("aaa", b"a"), ("bbb", b"b")):
                member = tarfile.TarInfo(name)
                member.size = len(payload)
                bundle.addfile(member, io.BytesIO(payload))

    destination = tmp_path / "bounded-paths-out"
    with pytest.raises(DownloadAuditError, match="archive_path_bytes_limit_exceeded"):
        safe_extract_archive(archive, destination, 1024)
    assert not destination.exists()


def test_archive_member_path_has_individual_byte_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(kaggle_download, "MAX_ARCHIVE_PATH_BYTES", 3)
    archive = tmp_path / "long-path.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("long", b"x")

    with pytest.raises(DownloadAuditError, match="archive_path_length_limit_exceeded"):
        safe_extract_archive(archive, tmp_path / "long-path-out", 1024)


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
            return SimpleNamespace(sha="a" * 40, cardData={"license": "cc-by-4.0"})

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
    assert calls["list_repo_tree"] == ("SEKOIA2900/VO-US", "dataset", "a" * 40, True, False)
    assert calls["snapshot_download"]["revision"] == "a" * 40
    assert calls["snapshot_download"]["allow_patterns"] == ["README.md", "voicebank.zip"]
    assert result["resolved_revision"] == "a" * 40
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
            return SimpleNamespace(sha="a" * 40, cardData=None)

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



def test_download_dataset_rejects_non_commit_revision_before_listing_or_download(tmp_path, monkeypatch):
    calls = []

    class FakeApi:
        def __init__(self, token=None):
            pass

        def dataset_info(self, repo_id, revision):
            return SimpleNamespace(sha="not-a-commit-sha", cardData=None)

        def list_repo_tree(self, *args, **kwargs):
            calls.append("list_repo_tree")
            return []

    def fake_snapshot_download(**kwargs):
        calls.append("snapshot_download")

    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(HfApi=FakeApi, snapshot_download=fake_snapshot_download),
    )

    with pytest.raises(DownloadAuditError, match="dataset_revision_unresolved"):
        download_dataset(
            "https://huggingface.co/datasets/owner/repo",
            tmp_path / "dataset",
        )

    assert calls == []
    assert not (tmp_path / "dataset").exists()


@pytest.mark.parametrize("archive_kind", ("zip", "tar"))
def test_extract_rejects_archive_member_count_limit(tmp_path, monkeypatch, archive_kind):
    monkeypatch.setattr("scripts.kaggle_hf_download.MAX_ARCHIVE_MEMBERS", 1)
    archive = tmp_path / f"many-members.{archive_kind}"
    if archive_kind == "zip":
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("voice/oto.ini", "first")
            bundle.writestr("voice/sample.wav", b"RIFF")
    else:
        with tarfile.open(archive, "w") as bundle:
            for name, payload in (("voice/oto.ini", b"first"), ("voice/sample.wav", b"RIFF")):
                member = tarfile.TarInfo(name)
                member.size = len(payload)
                bundle.addfile(member, io.BytesIO(payload))

    destination = tmp_path / "limited-out"
    with pytest.raises(DownloadAuditError, match="archive_member_limit_exceeded"):
        safe_extract_archive(archive, destination, 1024)
    assert not destination.exists()


def test_select_relevant_files_rejects_excessive_file_count(monkeypatch):
    monkeypatch.setattr("scripts.kaggle_hf_download.MAX_SELECTED_FILES", 1)
    entries = [
        {"path": "bank-a/oto.ini", "size": 1},
        {"path": "bank-b/oto.ini", "size": 1},
    ]
    with pytest.raises(DownloadAuditError, match="selected_file_count_limit_exceeded"):
        select_relevant_files(entries)


@pytest.mark.parametrize("url", [
    "https://huggingface.co:invalid/datasets/owner/repo",
    "https://huggingface.co/datasets/owner/repo/tree/%2E%2E",
    "https://huggingface.co/datasets/owner/repo/tree/feature%2F..%2Fmain",
    "https://huggingface.co/datasets/owner/repo/tree/feature%2F%2Fbranch",
    "https://huggingface.co/datasets/owner/repo/tree/feature%0Abranch",
    "https://huggingface.co/datasets/owner/repo/tree/main/subfolder",
    "https://huggingface.co/datasets/owner/repo?download=1",
])
def test_parse_dataset_url_rejects_malformed_revision_or_extra_path(url):
    with pytest.raises(DownloadAuditError):
        parse_dataset_url(url)


def test_parse_dataset_url_rejects_encoded_slashes_in_repository_id():
    with pytest.raises(DownloadAuditError, match="dataset_url_has_invalid_repository_id"):
        parse_dataset_url("https://huggingface.co/datasets/owner%2Frepo/name")


def test_parse_dataset_url_rejects_non_string_and_oversized_input():
    with pytest.raises(DownloadAuditError, match="dataset_url_invalid"):
        parse_dataset_url(None)
    with pytest.raises(DownloadAuditError, match="dataset_url_invalid"):
        parse_dataset_url("x" * 2049)


@pytest.mark.parametrize("archive_kind", ("zip", "tar"))
def test_aggregate_archive_member_budget_applies_across_archives(
    tmp_path, monkeypatch, archive_kind
):
    monkeypatch.setattr(kaggle_download, "MAX_TOTAL_ARCHIVE_MEMBERS", 3)
    archives = []
    for index in range(2):
        archive = tmp_path / f"voice-{index}.{archive_kind}"
        if archive_kind == "zip":
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("Voice/oto.ini", "alias")
                bundle.writestr("Voice/sample.wav", b"RIFF")
        else:
            with tarfile.open(archive, "w") as bundle:
                for name, payload in (("Voice/oto.ini", b"alias"), ("Voice/sample.wav", b"RIFF")):
                    member = tarfile.TarInfo(name)
                    member.size = len(payload)
                    bundle.addfile(member, io.BytesIO(payload))
        archives.append(archive)

    processed = 0
    first_counter = [0]
    safe_extract_archive(
        archives[0], tmp_path / "first-out", 1024,
        maximum_members=3 - processed, member_counter=first_counter,
    )
    processed += first_counter[0]
    assert processed == 2

    second_counter = [0]
    with pytest.raises(
        DownloadAuditError, match="archive_total_member_limit_exceeded"
    ):
        safe_extract_archive(
            archives[1], tmp_path / "second-out", 1024,
            maximum_members=3 - processed, member_counter=second_counter,
        )
    assert second_counter == [1]
    assert not (tmp_path / "second-out").exists()


def test_archive_discovery_rejects_excessive_archive_count(tmp_path, monkeypatch):
    monkeypatch.setattr(kaggle_download, "MAX_ARCHIVES", 1)
    for index in range(2):
        with zipfile.ZipFile(tmp_path / f"bank-{index}.zip", "w") as bundle:
            bundle.writestr("oto.ini", "alias")

    with pytest.raises(DownloadAuditError, match="archive_count_limit_exceeded"):
        collect_archive_paths(tmp_path)


def test_tar_extraction_streams_without_caching_member_objects(tmp_path, monkeypatch):
    archive = tmp_path / "tar-stream.tar"
    with tarfile.open(archive, "w") as bundle:
        for name, payload in (("Voice/oto.ini", b"alias"), ("Voice/sample.wav", b"RIFF")):
            member = tarfile.TarInfo(name)
            member.size = len(payload)
            bundle.addfile(member, io.BytesIO(payload))

    original_open = tarfile.open
    opened = []

    def capture_open(*args, **kwargs):
        bundle = original_open(*args, **kwargs)
        opened.append(bundle)
        return bundle

    monkeypatch.setattr("scripts.kaggle_hf_download.tarfile.open", capture_open)
    destination = tmp_path / "tar-stream-out"
    written = safe_extract_archive(archive, destination, 1024)

    assert written == len(b"alias") + len(b"RIFF")
    assert (destination / "Voice" / "oto.ini").read_bytes() == b"alias"
    assert (destination / "Voice" / "sample.wav").read_bytes() == b"RIFF"
    # is_tarfile() opens the archive once for probing; the final open is the
    # actual r|* extraction stream. Its TarInfo cache must stay empty.
    assert len(opened) >= 2
    assert getattr(opened[-1], "stream", True) is True
    assert opened[-1].members == []
