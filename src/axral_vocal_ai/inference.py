"""File-backed, proposal-only pitch-delta inference runtime.

The runtime emits sparse midpoint proposals only. It never edits a project,
changes a pitch curve, reads audio, or invokes the production renderer.
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
        """Return one bounded midpoint proposal for each unambiguous voiced note."""
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

            midpoint = (note.start_sec + note.end_sec) / 2.0
            duration = note.end_sec - note.start_sec
            features = (
                1.0,
                note.midi_note / 127.0,
                0.5,
                0.25,
                duration,
            )
            if len(features) != len(FEATURE_NAMES):
                raise RuntimeError("runtime feature contract is inconsistent")
            delta = self._model.predict_features(features)
            if abs(delta) > MAX_PREDICTION_DELTA_SEMITONES:
                # The model already bounds output; retain a defensive assertion.
                raise RuntimeError("model output exceeded the pitch-delta safety bound")
            if delta != 0.0:
                proposals.append(PitchDeltaPoint(time_sec=midpoint, delta_semitones=delta))

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

        # Treat the same public response gate as any future adapter boundary.
        validate_pitch_response(
            request,
            response,
            max_abs_delta_semitones=MAX_PREDICTION_DELTA_SEMITONES,
        )
        return response
