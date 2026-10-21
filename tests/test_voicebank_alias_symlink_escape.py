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
