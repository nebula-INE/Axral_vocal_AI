from __future__ import annotations

from pathlib import Path

import pytest

from axral_vocal_ai.oto_inventory import OtoEntry
from axral_vocal_ai.voicebank_alias import resolve_utau_alias


def test_symlink_to_file_outside_voicebank_is_rejected(tmp_path: Path) -> None:
    voicebank = tmp_path / "voicebank"
    voicebank.mkdir()
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"fixture only")
    link = voicebank / "alias.wav"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable on this platform")

    entry = OtoEntry(1, "alias.wav", "あ", 0.0, 100.0, -100.0, 20.0, 10.0)
    result = resolve_utau_alias("あ", 60, [entry], voicebank_root=voicebank)

    assert result.status == "invalid_sample_path"
    assert result.candidates == ()
    assert any("absolute or escapes" in issue for issue in result.issues)


def test_symlinked_directory_to_outside_voicebank_is_rejected(tmp_path: Path) -> None:
    voicebank = tmp_path / "voicebank"
    voicebank.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "alias.wav").write_bytes(b"fixture only")
    link_dir = voicebank / "linked"
    try:
        link_dir.symlink_to(outside_dir, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("directory symlink creation is unavailable on this platform")

    entry = OtoEntry(1, "linked/alias.wav", "あ", 0.0, 100.0, -100.0, 20.0, 10.0)
    result = resolve_utau_alias("あ", 60, [entry], voicebank_root=voicebank)

    assert result.status == "invalid_sample_path"
    assert result.candidates == ()
    assert any("absolute or escapes" in issue for issue in result.issues)

def test_broken_symlink_inside_voicebank_is_rejected(tmp_path: Path) -> None:
    voicebank = tmp_path / "voicebank"
    voicebank.mkdir()
    link = voicebank / "missing.wav"
    try:
        link.symlink_to(voicebank / "does-not-exist.wav")
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable on this platform")

    entry = OtoEntry(1, "missing.wav", "あ", 0.0, 100.0, -100.0, 20.0, 10.0)
    result = resolve_utau_alias("あ", 60, [entry], voicebank_root=voicebank)

    assert result.status == "invalid_sample_path"
    assert result.candidates == ()
    assert any("WAV file does not exist" in issue for issue in result.issues)


def test_symlink_loop_inside_voicebank_is_rejected(tmp_path: Path) -> None:
    voicebank = tmp_path / "voicebank"
    voicebank.mkdir()
    link = voicebank / "loop.wav"
    try:
        link.symlink_to(link)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable on this platform")

    entry = OtoEntry(1, "loop.wav", "あ", 0.0, 100.0, -100.0, 20.0, 10.0)
    result = resolve_utau_alias("あ", 60, [entry], voicebank_root=voicebank)

    assert result.status == "invalid_sample_path"
    assert result.candidates == ()
    assert any("absolute or escapes" in issue for issue in result.issues)
