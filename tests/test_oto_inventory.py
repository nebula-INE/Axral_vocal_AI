from __future__ import annotations

import pytest

from axral_vocal_ai.oto_inventory import parse_oto_ini


def test_parses_standard_entry_and_parameters() -> None:
    result = parse_oto_ini("あ.wav=あ,100,200,-300,50,20")
    assert result.issues == ()
    assert len(result.entries) == 1
    entry = result.entries[0]
    assert entry.wav_filename == "あ.wav"
    assert entry.alias == "あ"
    assert (entry.offset, entry.consonant, entry.cutoff, entry.preutterance, entry.overlap) == (
        100.0, 200.0, -300.0, 50.0, 20.0
    )


def test_normalizes_windows_separators_without_losing_subdirectories() -> None:
    result = parse_oto_ini("voice\\あ.wav=あ,0,100,-100,20,10")
    assert result.entries[0].wav_filename == "voice/あ.wav"


def test_duplicate_aliases_are_retained_in_order() -> None:
    result = parse_oto_ini("a.wav=a,0,1,-1,0,0\nb.wav=a,5,2,-2,1,1")
    assert [entry.alias for entry in result.entries] == ["a", "a"]
    assert [entry.wav_filename for entry in result.entries] == ["a.wav", "b.wav"]


def test_ignores_blank_lines_and_comments() -> None:
    result = parse_oto_ini("; comment\n\n# another comment\na.wav=a,0,1,-1,0,0")
    assert len(result.entries) == 1
    assert result.issues == ()


@pytest.mark.parametrize(
    "line",
    [
        "not an oto line",
        "=a,0,1,-1,0,0",
        "a.wav=,0,1,-1,0,0",
        "a.wav=a,0,1",
        "a.wav=a,zero,1,-1,0,0",
        "a.wav=a,nan,1,-1,0,0",
        "a.wav=a,inf,1,-1,0,0",
    ],
)
def test_reports_malformed_entries_instead_of_silently_dropping_them(line: str) -> None:
    result = parse_oto_ini(line)
    assert result.entries == ()
    assert len(result.issues) == 1
    assert result.issues[0].line_number == 1


def test_non_string_input_raises_type_error() -> None:
    with pytest.raises(TypeError):
        parse_oto_ini(None)  # type: ignore[arg-type]
