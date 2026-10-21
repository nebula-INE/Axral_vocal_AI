from __future__ import annotations

from pathlib import Path

import pytest

from axral_vocal_ai.oto_inventory import OtoEntry
from axral_vocal_ai.prefix_map import PrefixMapEntry
from axral_vocal_ai.voicebank_alias import resolve_utau_alias


def oto(line: int, filename: str, alias: str) -> OtoEntry:
    return OtoEntry(line, filename, alias, 0.0, 100.0, -100.0, 20.0, 10.0)


def test_resolves_alias_after_prefix_map() -> None:
    result = resolve_utau_alias(
        "あ", 65, [oto(1, "a.wav", "あ_F4")],
        [PrefixMapEntry(boundary=65, prefix="", suffix="_F4")],
    )
    assert result.status == "resolved"
    assert result.mapped_alias == "あ_F4"
    assert result.candidates[0].entry.wav_filename == "a.wav"


def test_duplicate_aliases_are_reported_as_ambiguous() -> None:
    result = resolve_utau_alias("あ", 60, [oto(1, "a.wav", "あ"), oto(2, "b.wav", "あ")])
    assert result.status == "ambiguous"
    assert len(result.candidates) == 2
    assert any("no candidate was selected" in issue for issue in result.issues)


def test_root_validation_returns_existing_file(tmp_path: Path) -> None:
    (tmp_path / "voice.wav").write_bytes(b"not decoded by this layer")
    result = resolve_utau_alias("あ", 60, [oto(1, "voice.wav", "あ")], voicebank_root=tmp_path)
    assert result.status == "resolved"
    assert result.candidates[0].wav_path == (tmp_path / "voice.wav").resolve()


@pytest.mark.parametrize("filename", ["../outside.wav", "/tmp/outside.wav", "C:\\outside.wav"])
def test_rejects_paths_outside_voicebank(tmp_path: Path, filename: str) -> None:
    result = resolve_utau_alias("あ", 60, [oto(1, filename, "あ")], voicebank_root=tmp_path)
    assert result.status == "invalid_sample_path"
    assert result.candidates == ()


def test_missing_wav_is_not_treated_as_resolved(tmp_path: Path) -> None:
    result = resolve_utau_alias("あ", 60, [oto(1, "missing.wav", "あ")], voicebank_root=tmp_path)
    assert result.status == "invalid_sample_path"
    assert any("does not exist" in issue for issue in result.issues)


def test_missing_alias_is_explicit() -> None:
    result = resolve_utau_alias("い", 60, [oto(1, "a.wav", "あ")])
    assert result.status == "missing_alias"
    assert result.candidates == ()


@pytest.mark.parametrize("note_num", [128, -1, float("nan"), float("inf"), float("-inf")])
def test_invalid_note_number_is_rejected(note_num: float) -> None:
    with pytest.raises(ValueError):
        resolve_utau_alias("あ", note_num, [])

def test_symlink_loop_is_rejected_without_crashing(tmp_path: Path) -> None:
    loop = tmp_path / "loop.wav"
    try:
        loop.symlink_to("loop.wav")
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable on this platform")

    result = resolve_utau_alias(
        "あ", 60, [oto(1, "loop.wav", "あ")], voicebank_root=tmp_path
    )

    assert result.status == "invalid_sample_path"
    assert result.candidates == ()
    assert any("absolute or escapes" in issue for issue in result.issues)
