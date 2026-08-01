"""Model bundle loading and validation.

The bundle is self-describing ({model, features, classes, trained_at,
version}); feature ORDER always comes from the bundle, never from importing
the training module. Boot validates that the bundle's feature SET matches
what this code computes — a mismatch means artifact and code have drifted,
and the only safe move is to refuse to serve.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import joblib

from triage.train.features import FEATURE_COLUMNS

# the export-block columns the plugin supplies alongside day_features
DAILY_COLUMNS = ("pi", "coverage", "rain_mm")

BUNDLE_KEYS = ("model", "features", "classes", "trained_at", "version")


@dataclass(frozen=True)
class Bundle:
    model: object
    features: list[str]
    classes: list[str]
    trained_at: str
    version: str


def load_bundle(path: Path) -> Bundle:
    raw = joblib.load(path)
    missing = [k for k in BUNDLE_KEYS if k not in raw]
    if missing:
        raise RuntimeError(
            f"bundle {path} lacks {missing} — retrain with the current save step"
        )
    computable = set(FEATURE_COLUMNS) | set(DAILY_COLUMNS)
    declared = set(raw["features"])
    if declared != computable:
        raise RuntimeError(
            "bundle/plugin feature drift: "
            f"bundle-only {sorted(declared - computable)}, "
            f"plugin-only {sorted(computable - declared)}"
        )
    return Bundle(
        model=raw["model"],
        features=[str(f) for f in raw["features"]],
        classes=[str(c) for c in raw["classes"]],
        trained_at=str(raw["trained_at"]),
        version=str(raw["version"]),
    )
