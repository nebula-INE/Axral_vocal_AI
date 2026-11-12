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
MAX_DOWNLOAD_MB = DEFAULT_MAX_DOWNLOAD_MB
MAX_EXTRACTED_MB = DEFAULT_MAX_EXTRACTED_MB
MAX_ARCHIVE_MEMBERS = 100_000
MAX_TOTAL_ARCHIVE_MEMBERS = 250_000
MAX_ARCHIVES = 512
MAX_SELECTED_FILES = 250_000
MAX_HUB_PATH_BYTES = 4096
MAX_SELECTED_PATH_BYTES = 16 * 1024 * 1024
MAX_ARCHIVE_PATH_BYTES = 4096
MAX_TOTAL_ARCHIVE_PATH_BYTES = 16 * 1024 * 1024


class _DiscardTarMembers(list):
    """Prevent TarFile from retaining every TarInfo while reading a stream."""

    def append(self, member):
        # TarFile.next() appends here on Python versions before stream=True.
        return None
ARCHIVE_SUFFIXES = (".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".tbz2", ".txz", ".zip", ".uar", ".tar")


class DownloadAuditError(RuntimeError):
    """A predictable acquisition or extraction failure."""


@dataclass(frozen=True)
class HubFile:
    path: str
    size: int


def parse_dataset_url(value: str) -> tuple[str, str]:
    """Return (dataset repo ID, revision) from a Hugging Face dataset URL.

    Accept the dataset landing page or an exact /tree/<revision> page.
    Encode slashes inside branch names as %2F to avoid confusing them with
    a folder path beneath the revision.
    """
    if not isinstance(value, str) or not value or len(value) > 2048:
        raise DownloadAuditError("dataset_url_invalid")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise DownloadAuditError("dataset_url_invalid_authority") from None
    if parsed.scheme != "https" or parsed.hostname != "huggingface.co":
        raise DownloadAuditError("dataset_url_must_use_https_huggingface_co")
    if parsed.username or parsed.password or port not in (None, 443):
        raise DownloadAuditError("dataset_url_has_unsupported_authority")
    if parsed.query or parsed.fragment:
        raise DownloadAuditError("dataset_url_query_or_fragment_not_supported")

    raw_parts = [part for part in parsed.path.split("/") if part]
    parts = [unquote(part) for part in raw_parts]
    if len(parts) < 3 or parts[0] != "datasets":
        raise DownloadAuditError("dataset_url_must_include_owner_and_repository")
    owner, name = parts[1], parts[2]
    repo_component = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}"
    if not re.fullmatch(repo_component, owner) or not re.fullmatch(repo_component, name):
        raise DownloadAuditError("dataset_url_has_invalid_repository_id")

    revision = "main"
    if len(parts) == 3:
        return f"{owner}/{name}", revision
    if len(parts) != 5 or parts[3] != "tree":
        raise DownloadAuditError("dataset_url_has_unsupported_path")
    revision = parts[4]
    revision_parts = revision.split("/")
    if (
        len(revision) > 128
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}", revision)
        or any(part in {"", ".", ".."} for part in revision_parts)
    ):
        raise DownloadAuditError("dataset_url_has_invalid_revision")
    return f"{owner}/{name}", revision


def _field(item: Any, key: str) -> Any:
    return item.get(key) if isinstance(item, dict) else getattr(item, key, None)


def _safe_hub_path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise DownloadAuditError("invalid_hub_path")
    try:
        encoded_length = len(value.encode("utf-8"))
    except UnicodeEncodeError:
        raise DownloadAuditError("invalid_hub_path") from None
    if encoded_length > MAX_HUB_PATH_BYTES:
        raise DownloadAuditError("hub_path_length_limit_exceeded")
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts or re.match(r"^[A-Za-z]:", normalized):
        raise DownloadAuditError("unsafe_hub_path")
    return path.as_posix()


def _exact_hub_allow_pattern(path: str) -> str:
    """Escape fnmatch metacharacters so allow_patterns selects one literal Hub path."""
    return path.replace("[", "[[]").replace("*", "[*]").replace("?", "[?]")


def _is_license_document_name(name: str) -> bool:
    """Recognize common and localized README/license file naming variants."""
    lowered = name.casefold()
    exact_names = {
        "readme", "license", "licence", "copying", "notice",
        "copyright", "terms", "eula",
    }
    variant_prefixes = tuple(
        f"{stem}{separator}"
        for stem in (
            "readme", "license", "licence", "copying",
            "notice", "copyright", "terms", "eula",
        )
        for separator in (".", "-", "_")
    )
    return lowered in exact_names or lowered.startswith(variant_prefixes)


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
    selected_path_bytes = 0
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
        if path not in selected:
            selected_path_bytes += len(path.encode("utf-8"))
            if selected_path_bytes > MAX_SELECTED_PATH_BYTES:
                raise DownloadAuditError("selected_path_bytes_limit_exceeded")
        selected[path] = HubFile(path, size)
        if len(selected) > MAX_SELECTED_FILES:
            raise DownloadAuditError("selected_file_count_limit_exceeded")
    return sorted(selected.values(), key=lambda item: item.path.casefold())


def enforce_download_limit(files: Iterable[HubFile], maximum_bytes: int) -> int:
    if (
        isinstance(maximum_bytes, bool)
        or not isinstance(maximum_bytes, int)
        or maximum_bytes < 1
        or maximum_bytes > MAX_DOWNLOAD_MB * 1024 * 1024
    ):
        raise DownloadAuditError("download_limit_out_of_range")
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
    relative = PurePosixPath(*parts)
    try:
        encoded_length = len(relative.as_posix().encode("utf-8"))
    except UnicodeEncodeError:
        raise DownloadAuditError("unsafe_archive_member") from None
    if encoded_length > MAX_ARCHIVE_PATH_BYTES:
        raise DownloadAuditError("archive_path_length_limit_exceeded")
    return relative


def _account_archive_path(relative: PurePosixPath, current_bytes: int) -> int:
    total = current_bytes + len(relative.as_posix().encode("utf-8"))
    if total > MAX_TOTAL_ARCHIVE_PATH_BYTES:
        raise DownloadAuditError("archive_path_bytes_limit_exceeded")
    return total


def _contains_japanese_text(value: str) -> bool:
    return any(
        "\u3040" <= char <= "\u30ff"
        or "\u3400" <= char <= "\u9fff"
        or "\uff00" <= char <= "\uffef"
        for char in value
    )


def _zip_member_path(info: zipfile.ZipInfo, *, allow_dot: bool = False) -> PurePosixPath:
    """Decode legacy CP932 ZIP names when the UTF-8 flag is absent.

    Python's ZIP reader follows the ZIP default and decodes unflagged names as
    CP437. Older Japanese voicebank archives often store CP932 bytes without
    setting the UTF-8 flag, which turns otherwise valid filenames into mojibake.
    Prefer an unambiguous Japanese-script CP932 candidate; preserve UTF-8 names,
    Unicode-path-extra names, and non-Japanese CP437 names unchanged.
    """
    filename = info.filename
    if not info.flag_bits & 0x800:
        try:
            legacy_candidate = filename.encode("cp437").decode("cp932")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
        else:
            if legacy_candidate != filename and _contains_japanese_text(legacy_candidate):
                filename = legacy_candidate
    return _safe_member_path(filename, allow_dot=allow_dot)


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


def _zip_central_directory_member_count(archive: Path) -> int:
    """Read the EOCD member count before ZipFile builds its in-memory index."""
    try:
        with archive.open("rb") as source:
            end_record = zipfile._EndRecData(source)
    except (AttributeError, OSError):
        raise DownloadAuditError("unsupported_or_invalid_archive") from None
    if end_record is None:
        raise DownloadAuditError("unsupported_or_invalid_archive")
    count = end_record[zipfile._ECD_ENTRIES_TOTAL]
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise DownloadAuditError("archive_member_count_invalid")
    return count


def _extract_zip(
    archive: Path, destination: Path, maximum_bytes: int,
    maximum_members: int, member_counter: list[int] | None,
) -> int:
    """Validate and extract ZIP members in one pass without a second index."""
    seen: set[str] = set()
    declared = 0
    written = 0
    path_bytes = 0
    # zipfile eagerly materializes a ZipInfo for every central-directory entry.
    # Inspect the small EOCD tail first so oversized indexes are rejected
    # before ZipFile allocates that per-member metadata list.
    central_count = _zip_central_directory_member_count(archive)
    if central_count > maximum_members:
        if member_counter is not None:
            member_counter[0] = maximum_members
        raise DownloadAuditError("archive_total_member_limit_exceeded")
    if central_count > MAX_ARCHIVE_MEMBERS:
        if member_counter is not None:
            member_counter[0] = MAX_ARCHIVE_MEMBERS
        raise DownloadAuditError("archive_member_limit_exceeded")
    with zipfile.ZipFile(archive) as bundle:
        infos = bundle.infolist()
        if len(infos) != central_count:
            raise DownloadAuditError("archive_member_count_mismatch")
        if member_counter is not None:
            member_counter[0] = len(infos)
        for info in infos:
            if info.is_dir():
                relative = _zip_member_path(info, allow_dot=True)
                path_bytes = _account_archive_path(relative, path_bytes)
                continue
            relative = _zip_member_path(info)
            path_bytes = _account_archive_path(relative, path_bytes)
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
            target = _safe_target(destination, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(info) as source, target.open("xb") as output:
                written += _copy_bounded(source, output, maximum_bytes - written, info.file_size)
    return written


def _extract_tar(
    archive: Path, destination: Path, maximum_bytes: int,
    maximum_members: int, member_counter: list[int] | None,
) -> int:
    """Stream TAR members so an archive cannot force a full member index into RAM."""
    seen: set[str] = set()
    declared = 0
    written = 0
    member_count = 0
    path_bytes = 0
    # Stream mode is supported by Python 3.10+ and avoids TarFile.getmembers()
    # caching every TarInfo object. Any later failure removes the partial tree.
    with tarfile.open(archive, "r|*") as bundle:
        # Python 3.10/3.12 do not expose TarFile(stream=True). Replacing the
        # member cache with a no-op list provides the same bounded-memory
        # behavior while keeping TarFile's forward-only stream reader.
        bundle.members = _DiscardTarMembers()
        if hasattr(bundle, "stream"):
            bundle.stream = True
        for member in bundle:
            member_count += 1
            if member_counter is not None:
                member_counter[0] = min(member_count, maximum_members)
            if member_count > maximum_members:
                raise DownloadAuditError("archive_total_member_limit_exceeded")
            if member_count > MAX_ARCHIVE_MEMBERS:
                raise DownloadAuditError("archive_member_limit_exceeded")
            if member.isdir():
                relative = _safe_member_path(member.name.rstrip("/") or ".", allow_dot=True)
                path_bytes = _account_archive_path(relative, path_bytes)
                continue
            relative = _safe_member_path(member.name)
            path_bytes = _account_archive_path(relative, path_bytes)
            if not member.isfile():
                raise DownloadAuditError("archive_link_or_special_file_rejected")
            key = relative.as_posix().casefold()
            if key in seen:
                raise DownloadAuditError("archive_duplicate_path")
            seen.add(key)
            declared += member.size
            if member.size < 0 or declared > maximum_bytes:
                raise DownloadAuditError("extracted_size_limit_exceeded")
            target = _safe_target(destination, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            source = bundle.extractfile(member)
            if source is None:
                raise DownloadAuditError("archive_member_read_failed")
            with source, target.open("xb") as output:
                written += _copy_bounded(source, output, maximum_bytes - written, member.size)
    return written


def safe_extract_archive(
    archive: Path, destination: Path, maximum_bytes: int, *,
    maximum_members: int = MAX_ARCHIVE_MEMBERS,
    member_counter: list[int] | None = None,
) -> int:
    """Extract ZIP/UAR-compatible or tar archives without traversing links."""
    if isinstance(maximum_members, bool) or not isinstance(maximum_members, int) or maximum_members < 0:
        raise DownloadAuditError("invalid_archive_member_budget")
    if member_counter is not None:
        if len(member_counter) != 1:
            raise DownloadAuditError("invalid_archive_member_counter")
        member_counter[0] = 0
    destination.mkdir(parents=True, exist_ok=False)
    try:
        if zipfile.is_zipfile(archive):
            return _extract_zip(archive, destination, maximum_bytes, maximum_members, member_counter)
        if tarfile.is_tarfile(archive):
            return _extract_tar(archive, destination, maximum_bytes, maximum_members, member_counter)
        raise DownloadAuditError("unsupported_or_invalid_archive")
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def collect_archive_paths(download_dir: Path) -> list[Path]:
    """Collect a bounded, deterministic list of supported archive paths."""
    archives: list[Path] = []
    for path in download_dir.rglob("*"):
        if path.is_file() and any(path.name.casefold().endswith(s) for s in ARCHIVE_SUFFIXES):
            archives.append(path)
            if len(archives) > MAX_ARCHIVES:
                raise DownloadAuditError("archive_count_limit_exceeded")
    return sorted(archives, key=lambda path: path.as_posix().casefold())


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
    if (
        isinstance(max_download_mb, bool)
        or not isinstance(max_download_mb, int)
        or not 1 <= max_download_mb <= MAX_DOWNLOAD_MB
    ):
        raise DownloadAuditError("download_limit_out_of_range")
    if (
        isinstance(max_extracted_mb, bool)
        or not isinstance(max_extracted_mb, int)
        or not 1 <= max_extracted_mb <= MAX_EXTRACTED_MB
    ):
        raise DownloadAuditError("extraction_limit_out_of_range")
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
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", revision):
        raise DownloadAuditError("dataset_revision_unresolved")
    entries = api.list_repo_tree(
        repo_id, repo_type="dataset", revision=revision, recursive=True, expand=False
    )
    selected = select_relevant_files(entries)
    if not selected:
        raise DownloadAuditError("no_relevant_voicebank_files")
    download_bytes = enforce_download_limit(selected, max_download_mb * 1024 * 1024)
    output_dir.mkdir(parents=True, exist_ok=True)
    download_dir = output_dir / "downloads"
    extracted_dir = output_dir / "extracted"
    download_dir.mkdir()
    extracted_dir.mkdir()
    snapshot_download(
        repo_id=repo_id, repo_type="dataset", revision=revision,
        local_dir=str(download_dir),
        allow_patterns=[_exact_hub_allow_pattern(item.path) for item in selected],
        token=token or None,
    )

    max_extracted_bytes = max_extracted_mb * 1024 * 1024
    extracted_bytes = 0
    archive_errors: list[str] = []
    archive_results: list[dict[str, Any]] = []
    archives = collect_archive_paths(download_dir)
    archive_members_processed = 0
    for index, archive in enumerate(archives, start=1):
        relative_archive = archive.relative_to(download_dir).as_posix()
        archive_size = archive.stat().st_size
        remaining = max_extracted_bytes - extracted_bytes
        if remaining <= 0:
            code = "extracted_size_limit_exceeded"
            archive_errors.append(code)
            archive_results.append({
                "path": relative_archive,
                "size_bytes": archive_size,
                "status": "skipped",
                "error_code": code,
                "extracted_bytes": 0,
            })
            continue
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", archive.name)[:80] or f"archive_{index}"
        destination = extracted_dir / f"{index:04d}_{safe_name}"
        member_counter = [0]
        try:
            written = safe_extract_archive(
                archive, destination, remaining,
                maximum_members=MAX_TOTAL_ARCHIVE_MEMBERS - archive_members_processed,
                member_counter=member_counter,
            )
            extracted_bytes += written
            archive_results.append({
                "path": relative_archive,
                "size_bytes": archive_size,
                "status": "extracted",
                "error_code": None,
                "extracted_bytes": written,
            })
        except Exception as exc:
            code = str(exc) if isinstance(exc, DownloadAuditError) else "archive_extraction_failed"
            archive_errors.append(code)
            archive_results.append({
                "path": relative_archive,
                "size_bytes": archive_size,
                "status": "failed",
                "error_code": code,
                "extracted_bytes": 0,
            })
        finally:
            archive_members_processed += member_counter[0]

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
        "archive_results": archive_results,
        "archive_errors": archive_errors,
        "extracted_bytes": extracted_bytes,
        "voicebank_roots": len(roots),
        "status": (
            "no_voicebank_roots_found" if not roots
            else "completed_with_archive_errors" if archive_errors
            else "completed"
        ),
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
