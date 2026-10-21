"""Filesystem-level UTAU voicebank analysis with conservative diagnostics.

This module inventories oto.ini and prefix.map files, validates WAV paths, and
reports duplicate aliases and parsing issues. It does not infer pronunciation,
choose ambiguous samples, or validate acoustic quality.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path, PureWindowsPath
from typing import Any

from axral_vocal_ai.oto_inventory import OtoEntry, parse_oto_ini
from axral_vocal_ai.prefix_map import PrefixMapEntry, parse_prefix_map
from axral_vocal_ai.wav_metadata import WavMetadata, inspect_wav
from axral_vocal_ai.wav_signal_audit import WavSignalAudit, inspect_pcm_signal


@dataclass(frozen=True)
class VoicebankIssue:
    severity: str
    code: str
    path: str
    line_number: int | None
    message: str


@dataclass(frozen=True)
class AliasPatternEvidence:
    pattern: str
    count: int
    examples: tuple[str, ...]


@dataclass(frozen=True)
class WavFileAudit:
    path: str
    metadata: WavMetadata | None
    error: str | None = None
    signal: WavSignalAudit | None = None


@dataclass(frozen=True)
class VoicebankAnalysis:
    root: str
    oto_files: tuple[str, ...]
    prefix_map_files: tuple[str, ...]
    entries: tuple[OtoEntry, ...]
    prefix_entries: tuple[PrefixMapEntry, ...]
    duplicate_aliases: tuple[tuple[str, tuple[str, ...]], ...]
    pattern_evidence: tuple[AliasPatternEvidence, ...]
    wav_files: tuple[WavFileAudit, ...]
    issues: tuple[VoicebankIssue, ...]

    @property
    def summary(self) -> dict[str, int]:
        return {
            "oto_files": len(self.oto_files),
            "prefix_map_files": len(self.prefix_map_files),
            "oto_entries": len(self.entries),
            "unique_aliases": len({entry.alias for entry in self.entries}),
            "duplicate_alias_groups": len(self.duplicate_aliases),
            "prefix_map_entries": len(self.prefix_entries),
            "wav_files_checked": len(self.wav_files),
            "wav_files_invalid": sum(
                item.error is not None
                or bool(
                    item.metadata
                    and any(
                        code in item.metadata.issues
                        for code in (
                            "riff_size_exceeds_file",
                            "chunk_size_exceeds_riff_boundary",
                            "chunk_truncated",
                            "missing_chunk_padding",
                        )
                    )
                )
                for item in self.wav_files
            ),
            # Unsupported formats are informational: they were not decoded,
            # so they must not inflate the count of detected signal findings.
            "wav_files_with_signal_issues": sum(
                bool(item.signal and any(not code.endswith("_unsupported") for code in item.signal.issues))
                for item in self.wav_files
            ),
            "wav_files_digital_silence": sum(
                bool(item.signal and "digital_silence" in item.signal.issues)
                for item in self.wav_files
            ),
            "wav_files_near_silence": sum(
                bool(item.signal and "near_silence" in item.signal.issues)
                for item in self.wav_files
            ),
            "wav_files_clipping_suspected": sum(
                bool(item.signal and "clipping_suspected" in item.signal.issues)
                for item in self.wav_files
            ),
            "errors": sum(issue.severity == "error" for issue in self.issues),
            "warnings": sum(issue.severity == "warning" for issue in self.issues),
        }

    def to_dict(self, *, include_root_path: bool = True) -> dict[str, Any]:
        """Return a JSON-ready report, optionally redacting local filesystem paths."""
        report = {
            "schema_version": 1,
            "root": self.root if include_root_path else None,
            "summary": self.summary,
            "oto_files": list(self.oto_files),
            "prefix_map_files": list(self.prefix_map_files),
            "entries": [asdict(entry) for entry in self.entries],
            "prefix_entries": [asdict(entry) for entry in self.prefix_entries],
            "duplicate_aliases": [
                {"alias": alias, "locations": list(locations)}
                for alias, locations in self.duplicate_aliases
            ],
            "pattern_evidence": [asdict(item) for item in self.pattern_evidence],
            "wav_files": [
                {
                    "path": item.path,
                    "metadata": (
                        {**asdict(item.metadata), "path": item.path}
                        if item.metadata else None
                    ),
                    "error": (
                        item.error.replace(self.root + os.sep, "")
                        if not include_root_path and item.error else item.error
                    ),
                    "signal": asdict(item.signal) if item.signal else None,
                }
                for item in self.wav_files
            ],
            "issues": [asdict(issue) for issue in self.issues],
        }
        if include_root_path:
            return report

        # Redact the root wherever it appears, not only in the top-level field.
        # Exception messages from filesystem operations can otherwise leak the
        # user's local directory through issue/wav error strings.
        roots = {
            self.root,
            self.root.replace("/", "\\"),
            self.root.replace("\\", "/"),
        }

        def redact(value: Any) -> Any:
            if isinstance(value, str):
                for root in roots:
                    if root:
                        value = value.replace(root, "<voicebank>")
                return value
            if isinstance(value, list):
                return [redact(item) for item in value]
            if isinstance(value, dict):
                return {key: redact(item) for key, item in value.items()}
            return value

        report["root"] = None
        return redact(report)

    def to_json(self, *, indent: int = 2, include_root_path: bool = True) -> str:
        return json.dumps(
            self.to_dict(include_root_path=include_root_path),
            ensure_ascii=False,
            indent=indent,
        )


def _read_text(path: Path) -> str:
    """Read common Japanese Windows voicebank encodings without data loss."""
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp932"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeError("File is not valid UTF-8 or CP932 text")


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _resolve_case_insensitive(root: Path, candidate: Path) -> Path:
    """Resolve an existing path with VO-SE's case-insensitive component fallback.

    Exact filesystem matches always win. The fallback is only used when a
    component's spelling differs; ambiguous case-folded matches are not guessed.
    """
    if candidate.is_file():
        return candidate
    try:
        relative = candidate.relative_to(root)
    except ValueError:
        return candidate

    current = root
    for component in relative.parts:
        if component in ("", "."):
            continue
        try:
            matches = sorted(
                child for child in current.iterdir()
                if child.name.casefold() == component.casefold()
            )
        except OSError:
            return candidate
        if len(matches) != 1:
            return candidate
        current = matches[0]

    return current if current.is_file() else candidate


def _alias_pattern(alias: str) -> str:
    """Classify spelling shape only; this is evidence, not a bank diagnosis."""
    parts = alias.strip().split()
    if len(parts) >= 2:
        return "space_separated_multi_token"
    if alias.strip():
        return "single_token"
    return "empty"


def analyze_voicebank(root: str | Path) -> VoicebankAnalysis:
    """Scan a voicebank directory recursively and produce actionable diagnostics.

    Each oto WAV filename is rebased relative to the voicebank root so nested
    oto.ini files remain addressable by the existing alias resolver. Duplicate
    aliases are preserved and reported rather than silently deduplicated.
    """
    root_path = Path(root).expanduser().resolve()
    if not root_path.exists():
        raise FileNotFoundError(f"Voicebank root does not exist: {root_path}")
    if not root_path.is_dir():
        raise NotADirectoryError(f"Voicebank root is not a directory: {root_path}")

    oto_paths: list[Path] = []
    prefix_paths: list[Path] = []
    issues: list[VoicebankIssue] = []

    def record_walk_error(exc: OSError) -> None:
        failed_path = Path(exc.filename) if exc.filename else root_path
        try:
            relative_path = _relative(root_path, failed_path.resolve())
        except (ValueError, OSError, RuntimeError):
            relative_path = str(exc.filename or root_path)
        issues.append(VoicebankIssue(
            "error", "directory_scan_failed", relative_path, None,
            f"Could not scan directory: {exc}",
        ))

    for directory, dirnames, filenames in os.walk(root_path, onerror=record_walk_error):
        current_dir = Path(directory)
        kept_dirnames: list[str] = []
        for name in sorted(dirnames):
            if name in {".git", "__pycache__"}:
                continue
            child_dir = current_dir / name
            # os.walk does not follow directory symlinks by default, but silently
            # skipping them makes an audit look more complete than it is. Report
            # them explicitly and never traverse them, even when they point inside
            # the bank; their contents are outside this scan's trust boundary.
            if child_dir.is_symlink():
                issues.append(VoicebankIssue(
                    "warning", "directory_symlink_skipped",
                    _relative(root_path, child_dir), None,
                    "Directory symlink was not scanned; copy or inspect its contents explicitly.",
                ))
                continue
            kept_dirnames.append(name)
        dirnames[:] = kept_dirnames
        for filename in sorted(filenames):
            lowered = filename.casefold()
            path = Path(directory) / filename
            if lowered == "oto.ini":
                oto_paths.append(path)
            elif lowered == "prefix.map":
                prefix_paths.append(path)

    oto_paths.sort()
    prefix_paths.sort()
    entries: list[OtoEntry] = []
    prefix_entries: list[PrefixMapEntry] = []
    first_prefix_boundary_file: dict[int, str] = {}
    reported_cross_file_boundaries: set[tuple[int, str]] = set()

    for path in oto_paths:
        relative_path = _relative(root_path, path)
        try:
            path.resolve().relative_to(root_path)
        except (ValueError, OSError, RuntimeError):
            issues.append(VoicebankIssue(
                "error", "oto_metadata_path_escape", relative_path, None,
                "oto.ini resolves outside the voicebank root; external metadata is not read.",
            ))
            continue
        try:
            parsed = parse_oto_ini(_read_text(path))
        except (OSError, UnicodeError) as exc:
            issues.append(VoicebankIssue("error", "oto_read_failed", relative_path, None, str(exc)))
            continue
        for issue in parsed.issues:
            issues.append(VoicebankIssue("warning", "oto_parse_issue", relative_path, issue.line_number, issue.message))
        for entry in parsed.entries:
            # Paths in oto.ini are relative to the oto.ini containing them.
            filename = entry.wav_filename
            windows = PureWindowsPath(filename)
            try:
                candidate = (
                    (path.parent / Path(filename)).resolve()
                    if not windows.is_absolute() and not windows.drive and not Path(filename).is_absolute()
                    else None
                )
            except (OSError, RuntimeError, ValueError):
                candidate = None
                issues.append(VoicebankIssue(
                    "error", "wav_path_resolution_failed", relative_path, entry.source_line,
                    "WAV path could not be resolved safely; the sample was not inspected.",
                ))
            if candidate is None:
                issues.append(VoicebankIssue("error", "absolute_wav_path", relative_path, entry.source_line,
                                             f"WAV path must be relative to oto.ini: {filename}"))
                rebased = filename
            else:
                try:
                    candidate.relative_to(root_path)
                except ValueError:
                    issues.append(VoicebankIssue("error", "wav_path_escape", relative_path, entry.source_line,
                                                 f"WAV path escapes voicebank root: {filename}"))
                    rebased = filename
                else:
                    candidate = _resolve_case_insensitive(root_path, candidate)
                    try:
                        candidate.resolve().relative_to(root_path)
                    except (OSError, RuntimeError):
                        issues.append(VoicebankIssue(
                            "error", "wav_path_resolution_failed", relative_path, entry.source_line,
                            "WAV path could not be resolved safely; the sample was not inspected.",
                        ))
                        rebased = filename
                        candidate = None
                    except ValueError:
                        issues.append(VoicebankIssue("error", "wav_path_escape", relative_path, entry.source_line,
                                                     f"WAV path resolves outside voicebank root: {filename}"))
                        rebased = filename
                        candidate = None
                    else:
                        rebased = candidate.relative_to(root_path).as_posix()
                        if not candidate.is_file():
                            issues.append(VoicebankIssue("error", "wav_missing", relative_path, entry.source_line,
                                                         f"WAV file not found: {rebased}"))
            entries.append(OtoEntry(entry.source_line, rebased, entry.alias, entry.offset,
                                    entry.consonant, entry.cutoff, entry.preutterance, entry.overlap))

    # Inspect each unique, existing sample once. This is structural metadata
    # validation only; it does not decode audio or claim phonetic correctness.
    wav_files: list[WavFileAudit] = []
    seen_wav_paths: set[str] = set()
    for entry in entries:
        relative_wav = entry.wav_filename
        if relative_wav in seen_wav_paths:
            continue
        seen_wav_paths.add(relative_wav)
        try:
            candidate = (root_path / relative_wav).resolve()
            candidate.relative_to(root_path)
        except (ValueError, OSError, RuntimeError):
            continue
        if not candidate.is_file():
            continue
        try:
            metadata = inspect_wav(candidate)
        except (OSError, ValueError) as exc:
            wav_files.append(WavFileAudit(relative_wav, None, str(exc)))
            issues.append(VoicebankIssue(
                "error", "wav_invalid", relative_wav, None,
                f"WAV metadata inspection failed: {exc}",
            ))
            continue
        signal = (inspect_pcm_signal(candidate) if metadata.audio_format_code == 1 else
                  WavSignalAudit("unsupported", 0, None, None, ("non_pcm_format_unsupported",)))
        wav_files.append(WavFileAudit(relative_wav, metadata, signal=signal))
        for code in metadata.issues:
            issues.append(VoicebankIssue(
                "warning", f"wav_{code}", relative_wav, None,
                f"WAV metadata check reported: {code}",
            ))
        for code in signal.issues:
            severity = "info" if code.endswith("_unsupported") else "warning"
            issue_code = "wav_" + code.split(":", 1)[0]
            issues.append(VoicebankIssue(severity, issue_code, relative_wav, None,
                                         "WAV signal check reported: " + code))

    for path in prefix_paths:
        relative_path = _relative(root_path, path)
        try:
            path.resolve().relative_to(root_path)
        except (ValueError, OSError, RuntimeError):
            issues.append(VoicebankIssue(
                "error", "prefix_map_path_escape", relative_path, None,
                "prefix.map resolves outside the voicebank root; external metadata is not read.",
            ))
            continue
        try:
            parsed = parse_prefix_map(_read_text(path))
        except (OSError, UnicodeError) as exc:
            issues.append(VoicebankIssue("error", "prefix_map_read_failed", relative_path, None, str(exc)))
            continue
        if path.parent != root_path:
            issues.append(VoicebankIssue("warning", "nested_prefix_map", relative_path, None,
                                         "Nested prefix.map found; entries are combined for inspection, but confirm which map the target renderer uses."))
        for issue in parsed.issues:
            issues.append(VoicebankIssue("warning", "prefix_map_parse_issue", relative_path, issue.line_number, issue.message))
        for entry in parsed.entries:
            first_file = first_prefix_boundary_file.setdefault(entry.boundary, relative_path)
            conflict_key = (entry.boundary, relative_path)
            if first_file != relative_path and conflict_key not in reported_cross_file_boundaries:
                issues.append(VoicebankIssue(
                    "warning", "prefix_map_boundary_conflict", relative_path, None,
                    f"Note boundary {entry.boundary} is also declared in {first_file}; "
                    "prefix.map files are combined for inspection, so selection may be ambiguous.",
                ))
                reported_cross_file_boundaries.add(conflict_key)
        prefix_entries.extend(parsed.entries)

    aliases: dict[str, list[str]] = defaultdict(list)
    pattern_counts: Counter[str] = Counter()
    pattern_examples: dict[str, list[str]] = defaultdict(list)
    for entry in entries:
        aliases[entry.alias].append(f"{entry.wav_filename} (oto.ini line {entry.source_line})")
        pattern = _alias_pattern(entry.alias)
        pattern_counts[pattern] += 1
        if len(pattern_examples[pattern]) < 5 and entry.alias not in pattern_examples[pattern]:
            pattern_examples[pattern].append(entry.alias)

    duplicates = tuple(
        (alias, tuple(locations))
        for alias, locations in sorted(aliases.items()) if len(locations) > 1
    )
    for alias, locations in duplicates:
        issues.append(VoicebankIssue("warning", "duplicate_alias", "", None,
                                     f"Alias {alias!r} occurs {len(locations)} times; selection requires review."))

    evidence = tuple(
        AliasPatternEvidence(pattern, pattern_counts[pattern], tuple(pattern_examples[pattern]))
        for pattern in sorted(pattern_counts)
    )
    if not oto_paths:
        issues.append(VoicebankIssue("error", "oto_not_found", ".", None, "No oto.ini file was found."))
    if not entries:
        issues.append(VoicebankIssue("error", "no_oto_entries", ".", None, "No valid oto.ini entries were parsed."))
    if not prefix_paths:
        issues.append(VoicebankIssue("warning", "prefix_map_not_found", ".", None,
                                     "No prefix.map found; pitch-specific alias mapping may be unavailable."))

    return VoicebankAnalysis(
        root=str(root_path),
        oto_files=tuple(_relative(root_path, path) for path in oto_paths),
        prefix_map_files=tuple(_relative(root_path, path) for path in prefix_paths),
        entries=tuple(entries),
        prefix_entries=tuple(prefix_entries),
        duplicate_aliases=duplicates,
        pattern_evidence=evidence,
        wav_files=tuple(wav_files),
        issues=tuple(issues),
    )
