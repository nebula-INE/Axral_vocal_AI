#!/usr/bin/env python3
"""Bounded Hugging Face UTAU voicebank download and safe archive extraction."""
from __future__ import annotations

import argparse
from hashlib import sha256
from dataclasses import dataclass
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tarfile
from typing import Any, Iterable
from urllib.parse import unquote, urlsplit
import zipfile

DEFAULT_MAX_DOWNLOAD_MB = 4096
DEFAULT_MAX_EXTRACTED_MB = 8192
ARCHIVE_SUFFIXES = (".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".tbz2", ".txz", ".zip", ".uar", ".tar")


class DownloadAuditError(RuntimeError):
    """A predictable acquisition or extraction failure."""


@dataclass(frozen=True)
class HubFile:
    path: str
    size: int


def parse_dataset_url(value: str) -> tuple[str, str]:
    """Return (dataset repo ID, revision) from a Hugging Face dataset URL."""
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname != "huggingface.co":
        raise DownloadAuditError("dataset_url_must_use_https_huggingface_co")
    if parsed.username or parsed.password or parsed.port not in (None, 443):
        raise DownloadAuditError("dataset_url_has_unsupported_authority")
    parts = [unquote(part) for part in parsed.path.split("/") if part]
    if len(parts) < 3 or parts[0] != "datasets":
        raise DownloadAuditError("dataset_url_must_include_owner_and_repository")
    owner, name = parts[1], parts[2]
    if not owner or not name or "/" in owner or "/" in name or "\\" in owner or "\\" in name:
        raise DownloadAuditError("dataset_url_has_invalid_repository_id")
    revision = "main"
    if len(parts) >= 5 and parts[3] == "tree":
        revision = parts[4]
        if not revision or revision in {".", ".."}:
            raise DownloadAuditError("dataset_url_has_invalid_revision")
    return f"{owner}/{name}", revision


def _field(item: Any, key: str) -> Any:
    return item.get(key) if isinstance(item, dict) else getattr(item, key, None)


def _safe_hub_path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise DownloadAuditError("invalid_hub_path")
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts or re.match(r"^[A-Za-z]:", normalized):
        raise DownloadAuditError("unsafe_hub_path")
    return path.as_posix()


def _is_license_document_name(name: str) -> bool:
    lowered = name.casefold()
    return (
        lowered == "readme.md"
        or lowered in {"license", "copying", "notice"}
        or lowered.startswith(("license.", "license-", "copying.", "copying-", "notice.", "notice-"))
    )


def _is_relevant(path: str) -> bool:
    lowered = path.casefold()
    name = PurePosixPath(lowered).name
    return (
        any(lowered.endswith(suffix) for suffix in ARCHIVE_SUFFIXES)
        or name in {"oto.ini", "prefix.map"}
        or PurePosixPath(lowered).suffix in {".wav", ".jsonl"}
        or _is_license_document_name(name)
    )


def collect_license_document_metadata(*scan_roots: Path) -> list[dict[str, Any]]:
    """Index README/license documents without treating their presence as permission."""
    records: list[dict[str, Any]] = []
    for scan_root in scan_roots:
        if not scan_root.exists():
            continue
        for path in sorted(scan_root.rglob("*"), key=lambda item: item.as_posix().casefold()):
            if path.is_symlink() or not path.is_file() or not _is_license_document_name(path.name):
                continue
            digest = sha256()
            size = 0
            with path.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    size += len(chunk)
                    digest.update(chunk)
            records.append({
                "source_root": scan_root.name,
                "path": path.relative_to(scan_root).as_posix(),
                "size_bytes": size,
                "sha256": digest.hexdigest(),
            })
    return records


def select_relevant_files(entries: Iterable[Any]) -> list[HubFile]:
    """Select voicebank archives, loose UTAU files, WAVs, and JSONL manifests."""
    selected: dict[str, HubFile] = {}
    for entry in entries:
        raw_path = _field(entry, "path")
        if raw_path is None:
            continue
        path = _safe_hub_path(raw_path)
        if not _is_relevant(path):
            continue
        size = _field(entry, "size")
        # Hub tree listings can also include directories; only files have sizes.
        if size is None:
            continue
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise DownloadAuditError("hub_file_size_unavailable")
        selected[path] = HubFile(path, size)
    return sorted(selected.values(), key=lambda item: item.path.casefold())


def enforce_download_limit(files: Iterable[HubFile], maximum_bytes: int) -> int:
    if maximum_bytes < 1:
        raise DownloadAuditError("invalid_download_limit")
    total = sum(item.size for item in files)
    if total > maximum_bytes:
        raise DownloadAuditError("download_size_limit_exceeded")
    return total


def _safe_member_path(name: str, allow_dot: bool = False) -> PurePosixPath:
    if not isinstance(name, str) or not name or "\x00" in name:
        raise DownloadAuditError("unsafe_archive_member")
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or normalized.startswith("//") or ".." in path.parts:
        raise DownloadAuditError("unsafe_archive_member")
    if re.match(r"^[A-Za-z]:", normalized):
        raise DownloadAuditError("unsafe_archive_member")
    parts = tuple(part for part in path.parts if part not in {"", "."})
    if not parts:
        if allow_dot:
            return PurePosixPath(".")
        raise DownloadAuditError("unsafe_archive_member")
    return PurePosixPath(*parts)


def _safe_target(root: Path, relative: PurePosixPath) -> Path:
    target = root.joinpath(*relative.parts)
    if not target.resolve(strict=False).is_relative_to(root.resolve()):
        raise DownloadAuditError("archive_path_escape")
    return target


def _copy_bounded(source: Any, output: Any, remaining: int, expected: int) -> int:
    copied = 0
    while True:
        chunk = source.read(min(1024 * 1024, remaining - copied + 1))
        if not chunk:
            break
        copied += len(chunk)
        if copied > remaining or copied > expected:
            raise DownloadAuditError("extracted_size_limit_exceeded")
        output.write(chunk)
    if copied != expected:
        raise DownloadAuditError("archive_member_size_mismatch")
    return copied


def _extract_zip(archive: Path, destination: Path, maximum_bytes: int) -> int:
    members: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
    seen: set[str] = set()
    declared = 0
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            if info.is_dir():
                _safe_member_path(info.filename.rstrip("/") or ".", allow_dot=True)
                continue
            relative = _safe_member_path(info.filename)
            mode = (info.external_attr >> 16) & 0o170000
            if mode not in (0, stat.S_IFREG):
                raise DownloadAuditError("archive_link_or_special_file_rejected")
            key = relative.as_posix().casefold()
            if key in seen:
                raise DownloadAuditError("archive_duplicate_path")
            seen.add(key)
            declared += info.file_size
            if info.file_size < 0 or declared > maximum_bytes:
                raise DownloadAuditError("extracted_size_limit_exceeded")
            members.append((info, relative))
        written = 0
        for info, relative in members:
            target = _safe_target(destination, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(info) as source, target.open("xb") as output:
                written += _copy_bounded(source, output, maximum_bytes - written, info.file_size)
    return written


def _extract_tar(archive: Path, destination: Path, maximum_bytes: int) -> int:
    members: list[tuple[tarfile.TarInfo, PurePosixPath]] = []
    seen: set[str] = set()
    declared = 0
    with tarfile.open(archive, "r:*") as bundle:
        for member in bundle.getmembers():
            if member.isdir():
                _safe_member_path(member.name.rstrip("/") or ".", allow_dot=True)
                continue
            relative = _safe_member_path(member.name)
            if not member.isfile():
                raise DownloadAuditError("archive_link_or_special_file_rejected")
            key = relative.as_posix().casefold()
            if key in seen:
                raise DownloadAuditError("archive_duplicate_path")
            seen.add(key)
            declared += member.size
            if member.size < 0 or declared > maximum_bytes:
                raise DownloadAuditError("extracted_size_limit_exceeded")
            members.append((member, relative))
        written = 0
        for member, relative in members:
            target = _safe_target(destination, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            source = bundle.extractfile(member)
            if source is None:
                raise DownloadAuditError("archive_member_read_failed")
            with source, target.open("xb") as output:
                written += _copy_bounded(source, output, maximum_bytes - written, member.size)
    return written


def safe_extract_archive(archive: Path, destination: Path, maximum_bytes: int) -> int:
    """Extract ZIP/UAR-compatible or tar archives without traversing links."""
    destination.mkdir(parents=True, exist_ok=False)
    try:
        if zipfile.is_zipfile(archive):
            return _extract_zip(archive, destination, maximum_bytes)
        if tarfile.is_tarfile(archive):
            return _extract_tar(archive, destination, maximum_bytes)
        raise DownloadAuditError("unsupported_or_invalid_archive")
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def discover_voicebank_roots(*scan_roots: Path) -> list[Path]:
    """Return outer voicebank roots, grouping nested oto.ini files together."""
    candidates: set[Path] = set()
    for scan_root in scan_roots:
        if not scan_root.exists():
            continue
        for current, dirnames, filenames in os.walk(scan_root, followlinks=False):
            current_path = Path(current)
            dirnames[:] = sorted(
                name for name in dirnames
                if not name.startswith(".") and not (current_path / name).is_symlink()
            )
            if any(name.casefold() == "oto.ini" for name in filenames):
                candidates.add(current_path.resolve())
    return sorted(
        (candidate for candidate in candidates
         if not any(parent in candidates for parent in candidate.parents)),
        key=lambda path: path.as_posix().casefold(),
    )


def download_dataset(
    dataset_url: str,
    output_dir: Path,
    *,
    token: str | None = None,
    max_download_mb: int = DEFAULT_MAX_DOWNLOAD_MB,
    max_extracted_mb: int = DEFAULT_MAX_EXTRACTED_MB,
) -> dict[str, Any]:
    """Resolve a pinned revision, download only selected files, and extract archives."""
    try:
        from huggingface_hub import HfApi, snapshot_download
    except ImportError as exc:
        raise DownloadAuditError("huggingface_hub_not_installed") from exc

    repo_id, requested_revision = parse_dataset_url(dataset_url)
    api = HfApi(token=token or None)
    info = api.dataset_info(repo_id, revision=requested_revision)
    revision = getattr(info, "sha", None)
    card_data = _field(info, "cardData") or _field(info, "card_data")
    dataset_card_license = _field(card_data, "license")
    if not isinstance(dataset_card_license, str) or not dataset_card_license.strip():
        dataset_card_license = None
    if not isinstance(revision, str) or not revision:
        raise DownloadAuditError("dataset_revision_unresolved")
    entries = api.list_repo_tree(
        repo_id, repo_type="dataset", revision=revision, recursive=True, expand=False
    )
    selected = select_relevant_files(entries)
    if not selected:
        raise DownloadAuditError("no_relevant_voicebank_files")
    download_bytes = enforce_download_limit(selected, max_download_mb * 1024 * 1024)
    if max_extracted_mb < 1:
        raise DownloadAuditError("invalid_extraction_limit")

    output_dir.mkdir(parents=True, exist_ok=True)
    download_dir = output_dir / "downloads"
    extracted_dir = output_dir / "extracted"
    download_dir.mkdir()
    extracted_dir.mkdir()
    snapshot_download(
        repo_id=repo_id, repo_type="dataset", revision=revision,
        local_dir=str(download_dir), allow_patterns=[item.path for item in selected],
        token=token or None,
    )

    max_extracted_bytes = max_extracted_mb * 1024 * 1024
    extracted_bytes = 0
    archive_errors: list[str] = []
    archives = sorted(
        (path for path in download_dir.rglob("*")
         if path.is_file() and any(path.name.casefold().endswith(s) for s in ARCHIVE_SUFFIXES)),
        key=lambda path: path.as_posix().casefold(),
    )
    for index, archive in enumerate(archives, start=1):
        remaining = max_extracted_bytes - extracted_bytes
        if remaining <= 0:
            archive_errors.append("extracted_size_limit_exceeded")
            continue
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", archive.name)[:80] or f"archive_{index}"
        destination = extracted_dir / f"{index:04d}_{safe_name}"
        try:
            extracted_bytes += safe_extract_archive(archive, destination, remaining)
        except Exception as exc:
            code = exc.code if isinstance(exc, DownloadAuditError) else "archive_extraction_failed"
            archive_errors.append(code)

    roots = discover_voicebank_roots(download_dir, extracted_dir)
    license_documents = collect_license_document_metadata(download_dir, extracted_dir)
    summary = {
        "dataset": repo_id,
        "requested_revision": requested_revision,
        "resolved_revision": revision,
        "dataset_card_license": dataset_card_license,
        "license_documents": license_documents,
        "selected_files": len(selected),
        "download_bytes": download_bytes,
        "archives_found": len(archives),
        "archive_errors": archive_errors,
        "extracted_bytes": extracted_bytes,
        "voicebank_roots": len(roots),
        "status": "completed" if roots else "no_voicebank_roots_found",
    }
    (output_dir / "download_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if not roots:
        raise DownloadAuditError("no_voicebank_roots_found")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_url")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-download-mb", type=int, default=DEFAULT_MAX_DOWNLOAD_MB)
    parser.add_argument("--max-extracted-mb", type=int, default=DEFAULT_MAX_EXTRACTED_MB)
    args = parser.parse_args()
    try:
        summary = download_dataset(
            args.dataset_url, args.output_dir,
            token=os.environ.get("HF_TOKEN"),
            max_download_mb=args.max_download_mb,
            max_extracted_mb=args.max_extracted_mb,
        )
    except DownloadAuditError as exc:
        print(json.dumps({"status": "failed", "error_code": str(exc)}, ensure_ascii=False))
        return 2
    except Exception as exc:
        print(json.dumps({
            "status": "failed",
            "error_code": f"unexpected_{type(exc).__name__.lower()}",
        }, ensure_ascii=False))
        return 2
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
