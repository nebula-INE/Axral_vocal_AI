"""Execute real VO-SE_vocal Desktop and Web pitch samplers in Axral's CI.

The integration checkout is supplied by .github/workflows/tests.yml. These tests
exercise production implementations without modifying or wrapping them. They
characterize Desktop linear sampling and the Web bridge's existing slew limit
and Hz-domain smoothing; they do not require identical interior samples.
"""
from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


def _desktop_engine_class():
    root_value = os.environ.get("VO_SE_VOCAL_ROOT")
    if not root_value:
        pytest.skip("VO_SE_VOCAL_ROOT is only configured by the integration workflow")

    root = Path(root_value).resolve()
    if not (root / "modules" / "audio" / "vo_se_engine.py").is_file():
        pytest.fail(f"VO_SE_VOCAL_ROOT does not contain the Desktop engine: {root}")

    root_text = str(root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)

    # Import the actual checked-out production implementation, not a copied
    # reimplementation or a fixture-derived approximation.
    module = importlib.import_module("modules.audio.vo_se_engine")
    return module.VO_SE_Engine


def test_real_desktop_sampler_linearly_interpolates_semitone_offsets() -> None:
    engine_class = _desktop_engine_class()
    engine = SimpleNamespace(aural_ai=None)
    note = SimpleNamespace(note_number=69, start_time=0.125, duration=0.1)
    events = [
        SimpleNamespace(time=0.125, value=0.0),
        SimpleNamespace(time=0.225, value=4.0),
    ]

    curve = engine_class._get_sampled_curve(
        engine, events, note, 5, is_pitch=True
    )
    expected_offsets = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    expected_hz = 440.0 * np.power(2.0, expected_offsets / 12.0)

    assert curve.dtype == np.float32
    assert curve == pytest.approx(expected_hz, rel=1e-5, abs=1e-4)


def test_real_desktop_sampler_preserves_negative_pitch_offsets() -> None:
    engine_class = _desktop_engine_class()
    engine = SimpleNamespace(aural_ai=None)
    note = SimpleNamespace(note_number=69, start_time=2.0, duration=0.1)
    events = [
        SimpleNamespace(time=2.0, value=0.0),
        SimpleNamespace(time=2.1, value=-2.0),
    ]

    curve = engine_class._get_sampled_curve(
        engine, events, note, 3, is_pitch=True
    )
    expected_hz = 440.0 * np.power(2.0, np.array([0.0, -1.0, -2.0]) / 12.0)

    assert curve == pytest.approx(expected_hz, rel=1e-5, abs=1e-4)



def test_actual_web_bridge_matches_desktop_sampler_for_shared_positive_pitch_curve() -> None:
    engine_class = _desktop_engine_class()
    root = Path(os.environ["VO_SE_VOCAL_ROOT"]).resolve()
    probe = Path(__file__).with_name("web_pitch_runtime_probe.mjs")
    completed = subprocess.run(
        ["node", str(probe)],
        cwd=root,
        env=os.environ.copy(),
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    web_curves = {key: np.asarray(value, dtype=np.float64) for key, value in json.loads(completed.stdout).items()}
    web_curve = web_curves["positive"]

    engine = SimpleNamespace(aural_ai=None)
    note = SimpleNamespace(note_number=69, start_time=0.0, duration=0.1)
    # Same semantic curve as the Web UST fixture: A4, 0 -> +2 semitones
    # over 100 ms, sampled at the inclusive 0/50/100 ms positions.
    events = [
        SimpleNamespace(time=0.0, value=0.0),
        SimpleNamespace(time=0.1, value=2.0),
    ]
    desktop_curve = engine_class._get_sampled_curve(
        engine, events, note, 3, is_pitch=True
    )

    assert web_curve.shape == desktop_curve.shape == (3,)
    # Both runtimes agree at the endpoints. The Web bridge then applies its
    # existing three-point smoothing in Hz, so the midpoint is not the raw
    # linearly interpolated Desktop midpoint.
    assert web_curve[[0, 2]] == pytest.approx(desktop_curve[[0, 2]], rel=1e-7, abs=1e-7)
    expected_web_midpoint = 0.25 * desktop_curve[0] + 0.50 * desktop_curve[1] + 0.25 * desktop_curve[2]
    assert web_curve[1] == pytest.approx(expected_web_midpoint, rel=1e-7, abs=1e-7)
    assert web_curve[1] != pytest.approx(desktop_curve[1], rel=1e-7, abs=1e-7)



def test_actual_web_bridge_matches_desktop_sampler_for_shared_negative_pitch_curve() -> None:
    engine_class = _desktop_engine_class()
    root = Path(os.environ["VO_SE_VOCAL_ROOT"]).resolve()
    probe = Path(__file__).with_name("web_pitch_runtime_probe.mjs")
    completed = subprocess.run(
        ["node", str(probe)],
        cwd=root,
        env=os.environ.copy(),
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    web_curves = {key: np.asarray(value, dtype=np.float64) for key, value in json.loads(completed.stdout).items()}
    engine = SimpleNamespace(aural_ai=None)
    note = SimpleNamespace(note_number=69, start_time=0.0, duration=0.1)
    events = [
        SimpleNamespace(time=0.0, value=0.0),
        SimpleNamespace(time=0.1, value=-2.0),
    ]
    desktop_curve = engine_class._get_sampled_curve(
        engine, events, note, 3, is_pitch=True
    )
    web_curve = web_curves["negative"]
    assert web_curve[[0, 2]] == pytest.approx(desktop_curve[[0, 2]], rel=1e-7, abs=1e-7)
    # As in the positive case, Web smoothing is applied after converting
    # semitone offsets to Hz and therefore changes the midpoint.
    expected_web_midpoint = 0.25 * desktop_curve[0] + 0.50 * desktop_curve[1] + 0.25 * desktop_curve[2]
    assert web_curve[1] == pytest.approx(expected_web_midpoint, rel=1e-7, abs=1e-7)
    assert web_curve[1] != pytest.approx(desktop_curve[1], rel=1e-7, abs=1e-7)


def test_actual_web_bridge_steep_bend_keeps_web_slew_limit_distinct_from_desktop() -> None:
    """A steep bend must expose the existing Web slew limit, not force false parity."""
    engine_class = _desktop_engine_class()
    root = Path(os.environ["VO_SE_VOCAL_ROOT"]).resolve()
    probe = Path(__file__).with_name("web_pitch_runtime_probe.mjs")
    completed = subprocess.run(
        ["node", str(probe)],
        cwd=root,
        env=os.environ.copy(),
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    web_curves = {key: np.asarray(value, dtype=np.float64) for key, value in json.loads(completed.stdout).items()}
    engine = SimpleNamespace(aural_ai=None)
    note = SimpleNamespace(note_number=69, start_time=0.0, duration=0.1)
    events = [
        SimpleNamespace(time=0.0, value=0.0),
        SimpleNamespace(time=0.1, value=10.0),
    ]
    desktop_curve = engine_class._get_sampled_curve(
        engine, events, note, 3, is_pitch=True
    )
    expected_web_raw = 440.0 * np.power(2.0, np.array([0.0, 4.0, 8.0]) / 12.0)
    expected_web = expected_web_raw.copy()
    expected_web[1] = 0.25 * expected_web_raw[0] + 0.50 * expected_web_raw[1] + 0.25 * expected_web_raw[2]
    assert web_curves["steep"] == pytest.approx(expected_web, rel=1e-7, abs=1e-7)
    assert desktop_curve == pytest.approx(
        440.0 * np.power(2.0, np.array([0.0, 5.0, 10.0]) / 12.0),
        rel=1e-5,
        abs=1e-4,
    )
    # The endpoints intentionally differ after Web slew limiting; this is a
    # characterization of existing behavior, not an instruction to reconcile it.
    assert web_curves["steep"][-1] != pytest.approx(desktop_curve[-1], rel=1e-4)
