#!/usr/bin/env python3
"""Download and audit UTAU voicebanks from a Hugging Face dataset repository."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tarfile
import tempfile
from typing import Any, Iterable
import zipfile

from axral_vocal_ai.voicebank_analysis import analyze_voicebank

DEFAULT_REPO_ID = "SEKOIA2900/VO-US"
ARCHIVE_SUFFIXES = (".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".tbz2", ".txz", ".zip", ".uar", ".tar")


class AuditFailure(RuntimeError):
    """Controlled error that is safe to expose in a summary."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class HubFile:
    path: str
    size: int


def _field(item: Any, name: str) -> Any:
    return item.get(name) if isinstance(item, dict) else getattr(item, name, None)


def _safe_repo_path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise AuditFailure("invalid_hub_file_path")
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts or re.match(r"^[A-Za-z]:", normalized):
        raise AuditFailure("unsafe_hub_file_path")
    return path.as_posix()


def is_relevant_voicebank_file(path: str) -> bool:
    """Keep supported UTAU archives, oto.ini, prefix.map and WAV files."""
    normalized = _safe_repo_path(path)
    lowered = normalized.casefold()
    name = PurePosixPath(lowered).name
    return (
        any(lowered.endswith(ext) for ext in ARCHIVE_SUFFIXES)
        or name in {"oto.ini", "prefix.map"}
        or PurePosixPath(lowered).suffix == ".wav"
    )


def select_relevant_files(entries: Iterable[Any], path_filter: str = "") -> list[HubFile]:
    """Select relevant files, optionally restricting Hub paths before download."""
    selected: dict[str, HubFile] = {}
    for entry in entries:
        raw_path = _field(entry, "path")
        if raw_path is None:
            continue
        path = _safe_repo_path(raw_path)
        if not is_relevant_voicebank_file(path):
            continue
        if path_filter and path_filter.casefold() not in path.casefold():
            continue
        size = _field(entry, "size")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise AuditFailure("hub_file_size_unavailable")
        selected[path] = HubFile(path, size)
    return sorted(selected.values(), key=lambda item: item.path.casefold())


def enforce_download_limit(files: Iterable[HubFile], maximum_bytes: int) -> int:
    total = sum(item.size for item in files)
    if maximum_bytes < 1:
        raise AuditFailure("invalid_download_limit")
    if total > maximum_bytes:
        raise AuditFailure("download_size_limit_exceeded")
    return total


def _safe_member_path(name: str, *, allow_current_directory: bool = False) -> PurePosixPath:
    if not isinstance(name, str) or not name or "\x00" in name:
        raise AuditFailure("unsafe_archive_member")
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        path.is_absolute() or ".." in path.parts
        or normalized.startswith("//")
        or re.match(r"^[A-Za-z]:", normalized)
    ):
        raise AuditFailure("unsafe_archive_member")
    parts = tuple(part for part in path.parts if part not in {"", "."})
    if not parts:
        if allow_current_directory and not path.is_absolute():
            return PurePosixPath(".")
        raise AuditFailure("unsafe_archive_member")
    return PurePosixPath(*parts)


def _safe_destination(root: Path, relative: PurePosixPath) -> Path:
    destination = root.joinpath(*relative.parts)
    if not destination.resolve(strict=False).is_relative_to(root.resolve()):
        raise AuditFailure("archive_path_escape")
    return destination


def _extract_zip(archive: Path, root: Path, max_bytes: int) -> int:
    entries: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
    seen: set[str] = set()
    total = 0
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            if info.is_dir():
                _safe_member_path(info.filename.rstrip("/") or ".", allow_current_directory=True)
                continue
            relative = _safe_member_path(info.filename)
            mode = (info.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                raise AuditFailure("archive_link_rejected")
            key = relative.as_posix().casefold()
            if key in seen:
                raise AuditFailure("archive_duplicate_path")
            seen.add(key)
            total += info.file_size
            if info.file_size < 0 or total > max_bytes:
                raise AuditFailure("extracted_size_limit_exceeded")
            entries.append((info, relative))
        written = 0
        for info, relative in entries:
            target = _safe_destination(root, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(info) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
                written += info.file_size
    return written


def _extract_tar(archive: Path, root: Path, max_bytes: int) -> int:
    entries: list[tuple[tarfile.TarInfo, PurePosixPath]] = []
    seen: set[str] = set()
    total = 0
    with tarfile.open(archive, "r:*") as bundle:
        for member in bundle.getmembers():
            if member.isdir():
                _safe_member_path(member.name.rstrip("/") or ".", allow_current_directory=True)
                continue
            relative = _safe_member_path(member.name)
            if not member.isfile():
                raise AuditFailure("archive_link_or_special_file_rejected")
            key = relative.as_posix().casefold()
            if key in seen:
                raise AuditFailure("archive_duplicate_path")
            seen.add(key)
            total += member.size
            if member.size < 0 or total > max_bytes:
                raise AuditFailure("extracted_size_limit_exceeded")
            entries.append((member, relative))
        written = 0
        for member, relative in entries:
            target = _safe_destination(root, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            source = bundle.extractfile(member)
            if source is None:
                raise AuditFailure("archive_member_read_failed")
            with source, target.open("xb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
                written += member.size
    return written


def safe_extract_archive(archive: Path, destination: Path, max_bytes: int) -> int:
    """Extract ZIP/UAR or tar data while rejecting traversal and links."""
    destination.mkdir(parents=True, exist_ok=False)
    try:
        if zipfile.is_zipfile(archive):
            return _extract_zip(archive, destination, max_bytes)
        if tarfile.is_tarfile(archive):
            return _extract_tar(archive, destination, max_bytes)
        raise AuditFailure("unsupported_or_invalid_archive")
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def discover_voicebank_roots(*roots_to_scan: Path) -> list[Path]:
    """Find oto.ini roots; group nested oto.ini files under their bank root."""
    candidates: set[Path] = set()
    for scan_root in roots_to_scan:
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
         if not any(other != candidate and other in candidate.parents for other in candidates)),
        key=lambda path: path.as_posix().casefold(),
    )


def summarize_analysis(index: int, analysis: Any) -> dict[str, Any]:
    """Return counts and issue codes only; never serialize aliases or paths."""
    issue_counts = Counter((item.severity, item.code) for item in analysis.issues)
    return {
        "bank_index": index,
        "counts": {
            key: int(value) for key, value in sorted(analysis.summary.items())
            if isinstance(value, int)
        },
        "issue_counts": {
            f"{severity}:{code}": count
            for (severity, code), count in sorted(issue_counts.items())
        },
    }


def build_markdown(summary: dict[str, Any]) -> str:
    totals = summary.get("totals", {})
    lines = [
        "# Hugging Face UTAU Voicebank Audit",
        "",
        f"- Status: **{summary.get('status', 'unknown')}**",
        f"- Dataset: {summary.get('dataset', DEFAULT_REPO_ID)}",
        f"- Resolved revision: {summary.get('resolved_revision') or 'unresolved'}",
        f"- Selected files: {summary.get('selected_files', 0)}",
        f"- Download size: {summary.get('download_bytes', 0)} bytes",
        f"- Voicebank roots audited: {summary.get('voicebank_roots', 0)}",
        f"- Archives rejected: {summary.get('archive_errors', 0)}",
        "",
        "| Metric | Count |",
        "| --- | ---: |",
    ]
    for key in ("oto_files", "oto_entries", "unique_aliases", "prefix_map_files",
                "prefix_map_entries", "wav_files_checked", "wav_files_invalid", "errors", "warnings"):
        lines.append(f"| {key} | {totals.get(key, 0)} |")
    lines.extend(["", "| Bank | OTO entries | WAV checked | Errors | Warnings |",
                  "| ---: | ---: | ---: | ---: | ---: |"])
    for bank in summary.get("banks", []):
        counts = bank.get("counts", {})
        lines.append(
            f"| {bank.get('bank_index')} | {counts.get('oto_entries', 0)} | "
            f"{counts.get('wav_files_checked', 0)} | {counts.get('errors', 0)} | "
            f"{counts.get('warnings', 0)} |"
        )
    lines.extend(["", "> Detailed parser output, aliases, filenames, local paths, and audio are not uploaded.", ""])
    if summary.get("fatal_error_code"):
        lines.append(f"Fatal error code: {summary['fatal_error_code']}")
    return "\n".join(lines)


def _write_summary(directory: Path, summary: dict[str, Any]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    markdown = build_markdown(summary) + "\n"
    (directory / "summary.md").write_text(markdown, encoding="utf-8")
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with Path(step_summary).open("a", encoding="utf-8") as output:
            output.write(markdown)


def _args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-id", default=DEFAULT_REPO_ID)
    parser.add_argument("--revision", default="main")
    parser.add_argument("--file-path-filter", default="")
    parser.add_argument("--voicebank-filter", default="")
    parser.add_argument("--max-download-mb", type=int, default=4096)
    parser.add_argument("--max-extracted-mb", type=int, default=8192)
    parser.add_argument("--fail-on", choices=("never", "warning", "error"), default="error")
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/hf-voicebank-audit"))
    return parser.parse_args(argv)


def run_audit(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    summary: dict[str, Any] = {
        "schema_version": 1, "dataset": args.repo_id, "requested_revision": args.revision,
        "resolved_revision": None, "status": "running", "selected_files": 0,
        "download_bytes": 0, "voicebank_roots": 0, "archive_errors": 0,
        "banks": [], "totals": {}, "fail_on": args.fail_on, "fatal_error_code": None,
    }
    try:
        try:
            from huggingface_hub import HfApi, snapshot_download
        except ImportError as exc:
            raise AuditFailure("huggingface_hub_not_installed") from exc
        logging.getLogger("huggingface_hub").setLevel(logging.WARNING)
        api = HfApi(token=os.environ.get("HF_TOKEN") or None)
        info = api.dataset_info(args.repo_id, revision=args.revision)
        revision_sha = getattr(info, "sha", None)
        if not isinstance(revision_sha, str) or not revision_sha:
            raise AuditFailure("dataset_revision_unresolved")
        summary["resolved_revision"] = revision_sha
        repo_files = api.list_repo_tree(
            args.repo_id, repo_type="dataset", revision=revision_sha,
            recursive=True, expand=False,
        )
        selected = select_relevant_files(repo_files, path_filter=args.file_path_filter)
        if not selected:
            code = "no_relevant_files_after_path_filter" if args.file_path_filter else "no_relevant_voicebank_files"
            raise AuditFailure(code)
        total_download = enforce_download_limit(
            selected, args.max_download_mb * 1024 * 1024
        )
        max_extracted = args.max_extracted_mb * 1024 * 1024
        if max_extracted < 1:
            raise AuditFailure("invalid_extraction_limit")
        summary["selected_files"] = len(selected)
        summary["download_bytes"] = total_download

        with tempfile.TemporaryDirectory(prefix="axral-hf-utau-") as temporary:
            temp_root = Path(temporary)
            download_root = temp_root / "downloaded"
            extract_root = temp_root / "extracted"
            extract_root.mkdir()
            snapshot_download(
                repo_id=args.repo_id, repo_type="dataset", revision=revision_sha,
                local_dir=str(download_root),
                allow_patterns=[item.path for item in selected],
                token=os.environ.get("HF_TOKEN") or None,
            )
            archives = sorted(
                (path for path in download_root.rglob("*")
                 if path.is_file() and any(path.name.casefold().endswith(s) for s in ARCHIVE_SUFFIXES)),
                key=lambda path: path.as_posix().casefold(),
            )
            extracted_size = 0
            archive_errors = 0
            for index, archive in enumerate(archives, start=1):
                remaining = max_extracted - extracted_size
                if remaining <= 0:
                    archive_errors += 1
                    continue
                safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", archive.name)[:80] or f"archive_{index}"
                destination = extract_root / f"{index:04d}_{safe_name}"
                try:
                    extracted_size += safe_extract_archive(archive, destination, remaining)
                except Exception:
                    archive_errors += 1

            voicebank_roots = discover_voicebank_roots(download_root, extract_root)
            summary["archive_errors"] = archive_errors
            if args.voicebank_filter:
                needle = args.voicebank_filter.casefold()
                voicebank_roots = [
                    root for root in voicebank_roots
                    if needle in root.as_posix().casefold()
                ]
            if not voicebank_roots:
                raise AuditFailure("no_voicebank_roots_found")

            totals: Counter[str] = Counter()
            banks: list[dict[str, Any]] = []
            for index, voicebank_root in enumerate(voicebank_roots, start=1):
                try:
                    analysis = analyze_voicebank(voicebank_root)
                except (OSError, ValueError, UnicodeError):
                    totals["errors"] += 1
                    banks.append({
                        "bank_index": index, "counts": {"errors": 1, "warnings": 0},
                        "issue_counts": {"error:analysis_failed": 1},
                    })
                    continue
                item = summarize_analysis(index, analysis)
                banks.append(item)
                totals.update(item["counts"])
            summary["voicebank_roots"] = len(voicebank_roots)
            summary["archive_errors"] = archive_errors
            summary["banks"] = banks
            summary["totals"] = dict(sorted(totals.items()))
            if archive_errors:
                summary["totals"]["errors"] = summary["totals"].get("errors", 0) + archive_errors

        errors = summary["totals"].get("errors", 0) > 0
        warnings = summary["totals"].get("warnings", 0) > 0
        failed = (args.fail_on == "error" and errors) or (
            args.fail_on == "warning" and (errors or warnings)
        )
        summary["status"] = "completed_with_findings" if failed else "completed"
        return summary, 1 if failed else 0
    except AuditFailure as exc:
        summary["status"] = "failed"
        summary["fatal_error_code"] = exc.code
        return summary, 2
    except Exception as exc:
        summary["status"] = "failed"
        summary["fatal_error_code"] = f"unexpected_{type(exc).__name__.lower()}"
        return summary, 2


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    summary, exit_code = run_audit(args)
    _write_summary(args.output_dir, summary)
    print(json.dumps({
        "status": summary["status"], "selected_files": summary["selected_files"],
        "voicebank_roots": summary["voicebank_roots"], "totals": summary["totals"],
        "fatal_error_code": summary["fatal_error_code"],
    }, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
