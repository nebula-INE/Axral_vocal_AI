from axral_vocal_ai.label_quality import audit_label_quality


def record(record_id, notes, points):
    return {
        "record_id": record_id,
        "input": {"notes": notes},
        "target": {"points": points},
    }


def test_label_quality_flags_unmapped_boundary_and_within_note_change():
    report = audit_label_quality([
        record(
            "r1",
            [
                {"start_sec": 0.0, "end_sec": 1.0, "midi_note": 60, "lyric": "a"},
                {"start_sec": 1.0, "end_sec": 2.0, "midi_note": 62, "lyric": "i"},
            ],
            [
                {"time_sec": 0.2, "delta_semitones": 0.0},
                {"time_sec": 0.3, "delta_semitones": 1.5},
                {"time_sec": 1.0, "delta_semitones": 0.2},
                {"time_sec": 1.5, "delta_semitones": 2.0},
            ],
        )
    ])
    assert report["labels_seen"] == 4
    assert report["labels_mapped_to_unique_voiced_note"] == 3
    assert report["labels_unmapped_or_ambiguous"] == 1
    assert report["labels_near_delta_bound"] == 1
    flags = report["records"][0]["flags"]
    assert any(flag["type"] == "within_note_change" for flag in flags)
    assert any(flag["type"] == "label_not_inside_unique_voiced_note" for flag in flags)
    assert any(flag["type"] == "label_near_delta_bound" for flag in flags)


def test_label_quality_does_not_compare_across_note_boundaries_or_overlaps():
    report = audit_label_quality([
        record(
            "r2",
            [
                {"start_sec": 0.0, "end_sec": 1.0, "midi_note": 60, "lyric": "a"},
                {"start_sec": 1.0, "end_sec": 2.0, "midi_note": 62, "lyric": "i"},
                {"start_sec": 1.5, "end_sec": 2.5, "midi_note": 64, "lyric": "u"},
            ],
            [
                {"time_sec": 0.5, "delta_semitones": 0.0},
                {"time_sec": 1.2, "delta_semitones": 1.8},
                {"time_sec": 1.7, "delta_semitones": -1.8},
            ],
        )
    ])
    # The latter two notes overlap and are excluded; no cross-note jump is scored.
    assert report["flagged_adjacent_segments"] == 0
    assert report["labels_unmapped_or_ambiguous"] == 2


def test_label_quality_empty_targets_are_reported_without_failure():
    report = audit_label_quality([record("empty", [], [])])
    assert report["status"] == "audited"
    assert report["labels_seen"] == 0
    assert report["records_with_flags"] == 0
