"""Validate metadata for reproducible, test-split-only pitch evaluations.

This module validates a report manifest; it does not run inference, certify
metrics, inspect audio, or start model training.
"""
from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any

_SUPPORTED_SCHEMAS = {
    "legacy-manifest-v1",
    "axral.pitch-training-example-1.0",
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class PitchEvaluationManifestError(ValueError):
    """Raised when an evaluation manifest is incomplete or unsafe."""


def validate_evaluation_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and return a safe summary of one evaluation manifest.

    Required fields include hashes for the dataset, held-out test snapshot,
    frozen split manifest, model artifact, and code revision. The split
    manifest digest records which frozen split policy/assignment artifact
    the evaluation claims to use; it does not verify the artifact itself.
    """
    if not isinstance(manifest, Mapping):
        raise PitchEvaluationManifestError("manifest must be a mapping")

    errors: list[str] = []
    required = (
        "evaluation_id",
        "schema",
        "dataset_snapshot_sha256",
        "test_dataset_snapshot_sha256",
        "split_manifest_sha256",
        "model_artifact_sha256",
        "code_revision",
        "seed",
        "evaluated_split",
        "evaluated_records",
        "metrics",
        "test_split_used_for_tuning",
    )
    for key in required:
        if key not in manifest:
            errors.append(f"missing_{key}")

    if errors:
        raise PitchEvaluationManifestError(";".join(errors))

    if not isinstance(manifest["evaluation_id"], str) or not manifest["evaluation_id"].strip():
        errors.append("invalid_evaluation_id")
    if not isinstance(manifest["schema"], str) or manifest["schema"] not in _SUPPORTED_SCHEMAS:
        errors.append("unsupported_schema")
    for key in (
        "dataset_snapshot_sha256",
        "test_dataset_snapshot_sha256",
        "split_manifest_sha256",
        "model_artifact_sha256",
        "code_revision",
    ):
        value = manifest[key]
        if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
            errors.append(f"invalid_{key}")
    seed = manifest["seed"]
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        errors.append("invalid_seed")
    if manifest["evaluated_split"] != "test":
        errors.append("evaluation_must_use_test_split")
    count = manifest["evaluated_records"]
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        errors.append("evaluated_records_must_be_positive")
    if manifest["test_split_used_for_tuning"] is not False:
        errors.append("test_split_must_not_be_used_for_tuning")

    metrics = manifest["metrics"]
    if not isinstance(metrics, Mapping) or not metrics:
        errors.append("metrics_must_be_nonempty_mapping")
    else:
        for name, value in metrics.items():
            if not isinstance(name, str) or not name.strip():
                errors.append("invalid_metric_name")
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                errors.append(f"invalid_metric_value:{name}")

    if errors:
        raise PitchEvaluationManifestError(";".join(errors))

    return {
        "evaluation_version": 1,
        "evaluation_id": manifest["evaluation_id"].strip(),
        "schema": manifest["schema"],
        "evaluated_split": "test",
        "evaluated_records": count,
        "metric_names": sorted(metrics),
        "reproducibility": {
            "dataset_snapshot_sha256": manifest["dataset_snapshot_sha256"],
            "test_dataset_snapshot_sha256": manifest["test_dataset_snapshot_sha256"],
            "split_manifest_sha256": manifest["split_manifest_sha256"],
            "model_artifact_sha256": manifest["model_artifact_sha256"],
            "code_revision": manifest["code_revision"],
            "seed": seed,
        },
        "status": "ready_for_human_review",
        "training_started": False,
        "warning": (
            "Metadata validation does not verify that hashes match artifacts, "
            "the frozen split assignment was followed, metrics are truthful, "
            "the test set is independent, or evaluation results are scientifically valid."
        ),
    }
