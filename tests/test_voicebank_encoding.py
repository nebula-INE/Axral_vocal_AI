from __future__ import annotations

from pathlib import Path

import pytest

from axral_vocal_ai.voicebank_analysis import analyze_voicebank


@pytest.mark.parametrize(
    ("encoding", "bom"),
    [
        ("utf-8", b""),
        ("utf-8", b"\xef\xbb\xbf"),
        ("cp932", b""),
        ("utf-16-le", b"\xff\xfe"),
        ("utf-16-be", b"\xfe\xff"),
    ],
)
def test_oto_ini_decodes_japanese_alias_without_mojibake(
    tmp_path: Path, encoding: str, bom: bytes
) -> None:
    metadata = "あ.wav=あ,0,100,-100,20,10\n"
    (tmp_path / "oto.ini").write_bytes(bom + metadata.encode(encoding))

    result = analyze_voicebank(tmp_path)

    assert len(result.entries) == 1
    assert result.entries[0].alias == "あ"
    assert result.entries[0].wav_filename == "あ.wav"
    assert not any(issue.code == "oto_parse_error" for issue in result.issues)


def test_utf8_is_preferred_over_cp932_for_bomless_metadata(tmp_path: Path) -> None:
    (tmp_path / "oto.ini").write_bytes("きゃ.wav=きゃ,0,100,-100,20,10\n".encode("utf-8"))

    result = analyze_voicebank(tmp_path)

    assert result.entries[0].alias == "きゃ"
    assert result.entries[0].wav_filename == "きゃ.wav"
