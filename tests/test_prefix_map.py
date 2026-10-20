from __future__ import annotations

import pytest

from axral_vocal_ai.prefix_map import (
    PrefixMapEntry,
    map_alias,
    note_name_to_midi,
    parse_prefix_map,
    select_prefix_map,
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [("C4", 60), ("F#4", 66), ("Bb3", 58), ("C-1", 0), ("G9", 127), ("not-a-note", None)],
)
def test_note_name_to_midi(name: str, expected: int | None) -> None:
    assert note_name_to_midi(name) == expected


def test_parses_legacy_suffix_rows_and_three_column_rows() -> None:
    result = parse_prefix_map("C1\t\t_C4\nF4\tC4/\t\n")
    assert result.issues == ()
    assert result.entries == (
        PrefixMapEntry(boundary=24, prefix="", suffix="_C4"),
        PrefixMapEntry(boundary=65, prefix="C4/", suffix=""),
    )


def test_selects_last_boundary_not_above_note() -> None:
    result = parse_prefix_map("C1\t\t_C4\nF4\t\t_F4\n")
    assert select_prefix_map(result.entries, 23) is None
    assert select_prefix_map(result.entries, 59).suffix == "_C4"
    assert select_prefix_map(result.entries, 65).suffix == "_F4"
    assert select_prefix_map(result.entries, 127).suffix == "_F4"


def test_selects_correct_boundary_from_unsorted_entries() -> None:
    entries = [
        PrefixMapEntry(boundary=65, prefix="", suffix="_F4"),
        PrefixMapEntry(boundary=24, prefix="", suffix="_C1"),
    ]

    assert select_prefix_map(entries, 60).suffix == "_C1"
    assert select_prefix_map(entries, 65).suffix == "_F4"


def test_applies_prefix_and_suffix_to_complete_alias() -> None:
    result = parse_prefix_map("C4\tC4/\t_C4\n")
    assert map_alias("a い", 60, result.entries) == "C4/a い_C4"
    assert map_alias("C4/a い", 60, result.entries) == "C4/a い_C4"


def test_preserves_sorted_boundaries() -> None:
    result = parse_prefix_map("F4\t\t_F4\nC1\t\t_C4")
    assert [entry.boundary for entry in result.entries] == [24, 65]


@pytest.mark.parametrize("line", ["bad line", "H4\t_X", "C10\t_X", "C4\tA\tB\tC"])
def test_reports_invalid_rows(line: str) -> None:
    result = parse_prefix_map(line)
    assert result.entries == ()
    assert len(result.issues) == 1
    assert result.issues[0].line_number == 1


def test_ignores_comments_and_blank_lines() -> None:
    result = parse_prefix_map("# header\n; comment\n\nC1\t\t_C4")
    assert len(result.entries) == 1
    assert result.issues == ()


def test_non_string_input_raises_type_error() -> None:
    with pytest.raises(TypeError):
        parse_prefix_map(None)  # type: ignore[arg-type]


def test_extremely_long_octave_field_is_reported_not_raised() -> None:
    result = parse_prefix_map("C" + ("9" * 5000) + "\\t_SUFFIX")
    assert result.entries == ()
    assert len(result.issues) == 1
    assert "Invalid or out-of-range note boundary" in result.issues[0].message


def test_duplicate_boundaries_are_reported_and_last_row_remains_deterministic() -> None:
    result = parse_prefix_map("C4\t\t_FIRST\nC4\t\t_LAST\n")

    assert len(result.entries) == 2
    assert len(result.issues) == 1
    assert result.issues[0].line_number == 2
    assert "Duplicate note boundary 60" in result.issues[0].message
    assert select_prefix_map(result.entries, 60).suffix == "_LAST"
