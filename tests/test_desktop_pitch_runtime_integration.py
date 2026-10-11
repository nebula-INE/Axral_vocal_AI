"""Execute the real VO-SE_vocal Desktop pitch sampler in Axral's CI.

The integration checkout is supplied by .github/workflows/tests.yml. These tests
exercise the current production Python sampler without modifying or wrapping it.
They characterize the no-AI baseline only; they do not assert Web parity.
"""
from __future__ import annotations

import importlib
import os
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
