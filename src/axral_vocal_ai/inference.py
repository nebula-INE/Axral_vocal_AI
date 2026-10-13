"""File-backed, proposal-only pitch-delta inference runtime.

The runtime never edits a project, changes a pitch curve, reads audio, or invokes
the production renderer. Sparse predict() remains backward compatible.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import PitchDeltaPoint, PitchRequest, PitchResponse
from .pitch_model import (
    FEATURE_NAMES,
    LinearPitchDeltaModel,
    MAX_PREDICTION_DELTA_SEMITONES,
)
from .response_validation import validate_pitch_response


class PitchModelLoadError(ValueError):
    """Raised when a model/report file cannot be safely loaded."""


class PitchDeltaInferenceRuntime:
    """Load a validated model artifact and produce non-destructive proposals."""

    def __init__(self, model: LinearPitchDeltaModel) -> None:
        if not isinstance(model, LinearPitchDeltaModel):
            raise TypeError("model must be a LinearPitchDeltaModel")
        self._model = model

    @classmethod
    def from_file(cls, path: str | Path) -> "PitchDeltaInferenceRuntime":
        """Load either a raw model artifact or a training report containing one."""
        try:
            with Path(path).open("r", encoding="utf-8") as stream:
                payload: Any = json.load(stream)
        except (OSError, json.JSONDecodeError) as exc:
            raise PitchModelLoadError(f"cannot read model artifact: {exc}") from exc

        if not isinstance(payload, dict):
            raise PitchModelLoadError("model file must contain a JSON object")

        if "model" in payload:
            if payload.get("status") != "experimental_training_complete":
                raise PitchModelLoadError("training report status is missing or unsupported")
            model_payload = payload["model"]
        else:
            model_payload = payload

        try:
            model = LinearPitchDeltaModel.from_dict(model_payload)
        except (TypeError, ValueError) as exc:
            raise PitchModelLoadError(f"invalid model artifact: {exc}") from exc
        return cls(model)

    def predict(self, request: PitchRequest) -> PitchResponse:
        """Return one bounded midpoint proposal per eligible note (legacy API)."""
        return self._predict(request, samples_per_note=1, include_zero=False)

    def predict_curve(
        self, request: PitchRequest, *, samples_per_note: int = 9
    ) -> PitchResponse:
        """Return evenly spaced, time-varying pitch proposals inside each note.

        Unlike predict(), this diagnostic sampling API retains zero-valued points:
        omitting them would make adjacent-jump and slope diagnostics misleading.
        Points are proposals only and are never applied to a project or renderer.
        """
        if type(samples_per_note) is not int or not 1 <= samples_per_note <= 101:
            raise ValueError("samples_per_note must be an integer in the range 1..101")
        return self._predict(
            request, samples_per_note=samples_per_note, include_zero=True
        )

    def _predict(
        self,
        request: PitchRequest,
        *,
        samples_per_note: int,
        include_zero: bool,
    ) -> PitchResponse:
        if not isinstance(request, PitchRequest):
            raise TypeError("request must be a PitchRequest")
        if not request.notes:
            return PitchResponse(
                status="no_change",
                warnings=("request contains no notes",),
                request_id=request.request_id,
            )

        proposals: list[PitchDeltaPoint] = []
        warnings: list[str] = []
        notes = request.notes

        for index, note in enumerate(notes):
            if note.voiced is False:
                continue
            if note.end_sec <= note.start_sec:
                warnings.append(f"note {index} skipped: zero-duration interval")
                continue

            # Do not guess which note should receive a proposal when intervals
            # overlap (including an explicit rest overlapping a voiced note).
            overlaps = any(
                other_index != index
                and max(note.start_sec, other.start_sec) < min(note.end_sec, other.end_sec)
                for other_index, other in enumerate(notes)
            )
            if overlaps:
                warnings.append(f"note {index} skipped: overlapping note intervals")
                continue

            duration = note.end_sec - note.start_sec
            for sample_index in range(1, samples_per_note + 1):
                phase = sample_index / (samples_per_note + 1)
                time_sec = note.start_sec + duration * phase
                features = (
                    1.0,
                    note.midi_note / 127.0,
                    phase,
                    phase * phase,
                    duration,
                )
                if len(features) != len(FEATURE_NAMES):
                    raise RuntimeError("runtime feature contract is inconsistent")
                delta = self._model.predict_features(features)
                if abs(delta) > MAX_PREDICTION_DELTA_SEMITONES:
                    raise RuntimeError("model output exceeded the pitch-delta safety bound")
                if include_zero or delta != 0.0:
                    proposals.append(
                        PitchDeltaPoint(time_sec=time_sec, delta_semitones=delta)
                    )

        if not proposals:
            response = PitchResponse(
                status="no_change",
                warnings=tuple(warnings) or ("model proposed no pitch changes",),
                request_id=request.request_id,
            )
        else:
            response = PitchResponse(
                status="ok",
                pitch_deltas=tuple(proposals),
                warnings=tuple(warnings),
                request_id=request.request_id,
            )

        validate_pitch_response(
            request,
            response,
            max_abs_delta_semitones=MAX_PREDICTION_DELTA_SEMITONES,
        )
        return response
