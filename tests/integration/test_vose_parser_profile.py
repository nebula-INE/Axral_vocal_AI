"""Optional integration tests against the real VO-SE_vocal parser.

Set VO_SE_VOCAL_ROOT to a checkout of nebula-INE/VO-SE_vocal. The normal
unit-test suite remains self-contained; CI checks out the production parser and
runs these tests against it without modifying that repository.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from axral_vocal_ai.voicebank.profile import build_voicebank_profile

VO_SE_VOCAL_ROOT = os.environ.get("VO_SE_VOCAL_ROOT")
if not VO_SE_VOCAL_ROOT:
    pytest.skip(
        "Set VO_SE_VOCAL_ROOT to run real OtoParser integration tests",
        allow_module_level=True,
    )

ROOT = Path(VO_SE_VOCAL_ROOT).resolve()
if not (ROOT / "modules" / "data" / "oto_parser.py").is_file():
    pytest.skip("VO_SE_VOCAL_ROOT does not contain modules/data/oto_parser.py", allow_module_level=True)
sys.path.insert(0, str(ROOT))

from modules.data.oto_parser import OtoParser  # noqa: E402


def _write_oto(folder: Path, lines: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "oto.ini").write_text(lines, encoding="utf-8")


def test_real_parser_cv_vcv_prefix_map_nested_bank_and_missing_samples(tmp_path):
    voice = tmp_path / "voice"
    voice.mkdir()
    for name in ("cv.wav", "vcv.wav", "c4.wav", "f4.wav"):
        (voice / name).write_bytes(b"RIFF")
    nested = voice / "D4"
    nested.mkdir()
    (nested / "nested.wav").write_bytes(b"RIFF")
    # Deliberately no missing.wav: OtoParser still creates an entry for it.
    (voice / "prefix.map").write_text(
        "C1\t\t_C4\nF4\t\t_F4\n",
        encoding="utf-8",
    )
    _write_oto(
        voice,
        "cv.wav=あ,0,0,0,50,0\n"
        "vcv.wav=a い,0,0,0,55,0\n"
        "c4.wav=あ_C4,0,0,0,60,0\n"
        "f4.wav=あ_F4,0,0,0,65,0\n"
        "missing.wav=欠損,0,0,0,0,0\n",
    )
    _write_oto(nested, "nested.wav=あ,0,0,0,70,0\n")

    parser = OtoParser()
    parser.load_voice_dir(str(voice), use_cache=False)

    # CV, VCV context, prefix.map pitch boundaries, and folder-scoped aliases
    # are resolved by the production parser rather than duplicated in Axral.
    assert parser.resolve_alias("あ") is not None
    assert parser.resolve_alias("い", "a").alias == "a い"
    assert parser.resolve_alias("あ", note_num=60).alias == "あ_C4"
    assert parser.resolve_alias("あ", note_num=65).alias == "あ_F4"
    assert parser.resolve_alias("D4/あ").preutterance == 70.0
    assert parser.get("欠損") is not None
    assert not Path(parser.get("欠損").wav_path).is_file()

    profile = build_voicebank_profile(
        parser,
        parser_version="VO-SE_vocal OtoParser integration",
        format_hints=("cv_aliases", "cvvc_aliases", "prefix_map"),
        pitch_bank_boundaries=(24.0, 65.0),
    )
    # Count existing unique WAV files only. The missing candidate and duplicate
    # unqualified/scoped aliases do not inflate the sample count.
    assert profile.sample_count == 4
    assert "vcv_aliases" in profile.format_hints
    assert "folder_qualified_aliases" in profile.format_hints
    assert "multipitch" in profile.format_hints
    assert not any(str(tmp_path) in token for token in profile.phoneme_inventory)
