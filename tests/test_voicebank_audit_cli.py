from __future__ import annotations

import json
from pathlib import Path
import struct

from axral_vocal_ai.voicebank_audit_cli import main


def write_silent_wav(path: Path) -> None:
    fmt = struct.pack("<HHIIHH", 1, 1, 44100, 88200, 2, 16)
    data = bytes(64 * 2)
    chunks = b"fmt " + struct.pack("<I", len(fmt)) + fmt
    chunks += b"data" + struct.pack("<I", len(data)) + data
    path.write_bytes(b"RIFF" + struct.pack("<I", len(chunks) + 4) + b"WAVE" + chunks)


def make_voicebank(root: Path, *, broken: bool = False) -> None:
    root.mkdir(parents=True)
    if broken:
        (root / "oto.ini").write_text(
            "missing.wav=あ,0,100,-100,20,10\n", encoding="utf-8"
        )
    else:
        write_silent_wav(root / "a.wav")
        (root / "oto.ini").write_text(
            "a.wav=あ,0,100,-100,20,10\n", encoding="utf-8"
        )
        (root / "prefix.map").write_text("C4\t-\t_C4\n", encoding="utf-8")


def test_cli_writes_json_to_stdout_and_returns_success_for_clean_bank(
    tmp_path: Path, capsys
) -> None:
    root = tmp_path / "voicebank"
    make_voicebank(root)

    status = main([str(root)])
    output = capsys.readouterr()

    assert status == 0
    report = json.loads(output.out)
    assert report["schema_version"] == 1
    assert report["summary"]["oto_entries"] == 1
    assert output.err == ""


def test_cli_writes_report_file_and_fails_on_errors_by_default(
    tmp_path: Path, capsys
) -> None:
    root = tmp_path / "voicebank"
    make_voicebank(root, broken=True)
    report_path = tmp_path / "reports" / "audit.json"

    status = main([str(root), "--output", str(report_path)])
    output = capsys.readouterr()

    assert status == 1
    assert output.out == ""
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["summary"]["errors"] >= 1
    assert report["issues"]


def test_cli_fail_on_warning_returns_one_when_warnings_exist(
    tmp_path: Path, capsys
) -> None:
    root = tmp_path / "voicebank"
    make_voicebank(root)

    status = main([str(root), "--fail-on", "warning"])
    output = capsys.readouterr()

    report = json.loads(output.out)
    assert report["summary"]["warnings"] >= 1
    assert status == 1
    assert output.err == ""


def test_cli_fail_on_warning_can_be_disabled(tmp_path: Path, capsys) -> None:
    root = tmp_path / "voicebank"
    make_voicebank(root, broken=True)

    status = main([str(root), "--fail-on", "never"])
    output = capsys.readouterr()

    assert status == 0
    assert json.loads(output.out)["summary"]["errors"] >= 1


def test_cli_returns_two_for_missing_voicebank(tmp_path: Path, capsys) -> None:
    status = main([str(tmp_path / "does-not-exist")])
    output = capsys.readouterr()

    assert status == 2
    assert output.out == ""
    assert "voicebank audit failed:" in output.err
