from axral_vocal_ai.contextual_alias_plan import AliasConvention, plan_contextual_aliases
from axral_vocal_ai.oto_inventory import OtoEntry


def oto(line: int, alias: str) -> OtoEntry:
    return OtoEntry(line, f"{line}.wav", alias, 0.0, 100.0, -100.0, 20.0, 10.0)


def test_cv_profile_uses_explicit_cv_template() -> None:
    result = plan_contextual_aliases(
        ["ア", "イ"], [60, 62], [oto(1, "ア"), oto(2, "CV:イ")],
        AliasConvention(strategy="cv", cv_template="CV:{current}"),
    )
    assert result.status == "resolved"
    assert [item.requested_alias for item in result.aliases] == ["ア", "CV:イ"]


def test_vcv_uses_explicit_previous_vowel_and_template() -> None:
    result = plan_contextual_aliases(
        ["ア", "イ"], [60, 62], [oto(1, "ア"), oto(2, "a イ")],
        AliasConvention(strategy="vcv", vowel_map={"ア": "a"}),
    )
    assert result.status == "resolved"
    assert [item.role for item in result.aliases] == ["initial", "vcv"]
    assert result.aliases[1].requested_alias == "a イ"


def test_vcv_does_not_guess_missing_vowel_mapping() -> None:
    result = plan_contextual_aliases(
        ["ア", "イ"], [60, 62], [oto(1, "ア"), oto(2, "a イ")],
        AliasConvention(strategy="vcv"),
    )
    assert result.status == "needs_review"
    assert result.aliases == ()
    assert "ア" in result.warnings[0]


def test_cvvc_emits_separate_onset_and_transition_lookups() -> None:
    result = plan_contextual_aliases(
        ["ア", "イ"], [60, 62],
        [oto(1, "ア"), oto(2, "CV:イ"), oto(3, "a イ")],
        AliasConvention(
            strategy="cvvc", cvvc_onset_template="CV:{current}",
            vowel_map={"ア": "a"},
        ),
    )
    assert result.status == "resolved"
    assert [item.role for item in result.aliases] == ["initial", "cvvc_onset", "vc_transition"]
    assert [item.requested_alias for item in result.aliases] == ["ア", "CV:イ", "a イ"]


def test_duplicate_alias_remains_ambiguous() -> None:
    result = plan_contextual_aliases(
        ["ア"], [60], [oto(1, "ア"), oto(2, "ア")], AliasConvention(strategy="cv"),
    )
    assert result.status == "needs_review"
    assert result.aliases[0].resolution.status == "ambiguous"
    assert len(result.aliases[0].resolution.candidates) == 2


def test_count_mismatch_emits_no_partial_lookup() -> None:
    result = plan_contextual_aliases(
        ["ア", "イ"], [60], [oto(1, "ア")], AliasConvention(strategy="cv"),
    )
    assert result.status == "note_mora_count_mismatch"
    assert result.aliases == ()
