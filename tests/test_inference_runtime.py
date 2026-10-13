import json

import pytest

from axral_vocal_ai.contracts import PitchNote, PitchRequest
from axral_vocal_ai.inference import PitchDeltaInferenceRuntime, PitchModelLoadError
from axral_vocal_ai.pitch_model import LinearPitchDeltaModel


def artifact(weights=(0.5, 0.0, 0.0, 0.0, 0.0)):
    return LinearPitchDeltaModel(weights=weights).to_dict()


def write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def runtime_for(tmp_path, weights=(0.5, 0.0, 0.0, 0.0, 0.0)):
    return PitchDeltaInferenceRuntime.from_file(
        write_json(tmp_path / "model.json", artifact(weights=weights))
    )


def test_runtime_loads_raw_artifact_and_proposes_bounded_midpoint(tmp_path):
    runtime = runtime_for(tmp_path)
    request = PitchRequest(
        request_id="req-1",
        notes=(PitchNote(start_sec=0.0, end_sec=2.0, midi_note=60, lyric="a"),),
    )

    response = runtime.predict(request)

    assert response.status == "ok"
    assert response.request_id == "req-1"
    assert len(response.pitch_deltas) == 1
    assert response.pitch_deltas[0].time_sec == pytest.approx(1.0)
    assert response.pitch_deltas[0].delta_semitones == pytest.approx(0.5)


def test_runtime_loads_training_report_wrapper(tmp_path):
    report = {
        "status": "experimental_training_complete",
        "model": artifact(),
    }
    runtime = PitchDeltaInferenceRuntime.from_file(
        write_json(tmp_path / "report.json", report)
    )
    assert isinstance(runtime, PitchDeltaInferenceRuntime)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"status": "failed", "model": artifact()},
        {"model": {"model_type": "unknown"}},
        {"model_type": "linear_ridge_pitch_delta", "weights": []},
    ],
)
def test_runtime_rejects_invalid_artifact_wrappers(tmp_path, payload):
    path = write_json(tmp_path / "bad.json", payload)
    with pytest.raises(PitchModelLoadError):
        PitchDeltaInferenceRuntime.from_file(path)


def test_runtime_skips_explicit_rests_and_overlapping_notes(tmp_path):
    runtime = runtime_for(tmp_path)
    request = PitchRequest(notes=(
        PitchNote(0.0, 1.0, 60, "a", voiced=False),
        PitchNote(1.0, 2.0, 62, "i"),
        PitchNote(1.5, 2.5, 64, "u"),
        PitchNote(3.0, 4.0, 65, "e"),
    ))

    response = runtime.predict(request)

    assert response.status == "ok"
    assert [point.time_sec for point in response.pitch_deltas] == [3.5]
    assert any("overlapping note intervals" in warning for warning in response.warnings)


def test_runtime_returns_no_change_for_empty_or_zero_prediction(tmp_path):
    runtime = runtime_for(tmp_path, weights=(0.0,) * 5)

    empty = runtime.predict(PitchRequest(notes=()))
    silent = runtime.predict(PitchRequest(notes=(
        PitchNote(0.0, 1.0, 60, "a"),
    )))

    assert empty.status == "no_change"
    assert silent.status == "no_change"
    assert not empty.pitch_deltas
    assert not silent.pitch_deltas


def test_runtime_rejects_unreadable_json(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(PitchModelLoadError, match="cannot read model artifact"):
        PitchDeltaInferenceRuntime.from_file(path)


def test_predict_curve_samples_note_phase_and_stays_inside_note(tmp_path):
    # phase^2 makes the expected output change across the note interval.
    runtime = runtime_for(tmp_path, weights=(0.0, 0.0, 0.0, 1.0, 0.0))
    request = PitchRequest(
        request_id="curve-1",
        notes=(PitchNote(2.0, 5.0, 60, "a"),),
    )

    response = runtime.predict_curve(request, samples_per_note=3)

    assert response.status == "ok"
    assert response.request_id == "curve-1"
    assert [point.time_sec for point in response.pitch_deltas] == pytest.approx(
        [2.75, 3.5, 4.25]
    )
    assert [point.delta_semitones for point in response.pitch_deltas] == pytest.approx(
        [1 / 16, 1 / 4, 9 / 16]
    )
    assert all(2.0 < point.time_sec < 5.0 for point in response.pitch_deltas)


def test_predict_curve_preserves_rest_and_overlap_guards(tmp_path):
    runtime = runtime_for(tmp_path)
    request = PitchRequest(notes=(
        PitchNote(0.0, 1.0, 60, "a", voiced=False),
        PitchNote(1.0, 2.0, 62, "i"),
        PitchNote(1.5, 2.5, 64, "u"),
        PitchNote(3.0, 4.0, 65, "e"),
    ))

    response = runtime.predict_curve(request, samples_per_note=2)

    assert response.status == "ok"
    assert [point.time_sec for point in response.pitch_deltas] == pytest.approx(
        [3 + 1 / 3, 3 + 2 / 3]
    )
    assert any("overlapping note intervals" in warning for warning in response.warnings)


@pytest.mark.parametrize("count", [0, -1, 102, True, 1.5])
def test_predict_curve_rejects_invalid_sample_counts(tmp_path, count):
    runtime = runtime_for(tmp_path)
    request = PitchRequest(notes=(PitchNote(0.0, 1.0, 60, "a"),))

    with pytest.raises(ValueError, match="samples_per_note"):
        runtime.predict_curve(request, samples_per_note=count)
