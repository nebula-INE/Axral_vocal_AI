import pytest

from axral_vocal_ai.evaluation import evaluate_stratified
from axral_vocal_ai.pitch_model import LinearPitchDeltaModel, TrainingExample


def example(record, bank, midi, target, split="test"):
    return TrainingExample(
        features=(1.0, midi / 127.0, 0.5, 0.25, 0.4),
        target=target,
        record_id=record,
        voicebank_id=bank,
        split=split,
    )


def test_evaluation_reports_overall_bank_and_pitch_range_metrics():
    model = LinearPitchDeltaModel(weights=(0.25, 0.0, 0.0, 0.0, 0.0))
    rows = [
        example("a", "bank-a", 60, 0.5),
        example("b", "bank-b", 84, -0.5),
    ]

    report = evaluate_stratified(rows, model, split="test")

    assert report["status"] == "evaluated"
    assert report["examples"] == 2
    assert report["overall"]["mae_semitones"] == pytest.approx(0.5)
    assert report["overall"]["rmse_semitones"] == pytest.approx(0.5)
    assert set(report["by_voicebank"]) == {"bank-a", "bank-b"}
    assert report["by_midi_range"]["midi_60_71"]["examples"] == 1
    assert report["by_midi_range"]["midi_84_127"]["examples"] == 1
    assert report["by_midi_range"]["midi_0_47"]["examples"] == 0


def test_evaluation_rejects_empty_or_mixed_split_rows():
    model = LinearPitchDeltaModel(weights=(0.0,) * 5)
    with pytest.raises(ValueError, match="no usable"):
        evaluate_stratified([], model, split="test")
    with pytest.raises(ValueError, match="all examples"):
        evaluate_stratified([example("a", "bank-a", 60, 0.0, "train")], model, split="test")


def test_evaluation_rejects_unknown_split():
    with pytest.raises(ValueError, match="split must be"):
        evaluate_stratified([example("a", "bank-a", 60, 0.0)], LinearPitchDeltaModel(weights=(0.0,) * 5), split="dev")
