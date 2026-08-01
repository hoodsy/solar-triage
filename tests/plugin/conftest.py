"""Shared plugin-test harness: env-driven app boot against the real bundle.

Unit tests never touch the network: BACKFILL_DAYS=0 and WEATHER=false by
default; individual tests override and stub the adapters.
"""

from pathlib import Path

import pytest

pytest.importorskip("fastapi")

REAL_BUNDLE = Path("model/model.joblib")

BASE_ENV = {
    "SITE_TZ": "Pacific/Auckland",
    "LAT": "-36.85",
    "LON": "174.76",
    "TILT": "25.0",
    "AZIMUTH": "0.0",
    "DC_KW": "2.0",
    "AC_KW": "1.9",
    "NODE_ID": "120",
    "POWER_SOURCE_ID": "Solar",
    "BACKFILL_DAYS": "0",
    "WEATHER": "false",
}


@pytest.fixture
def make_client(tmp_path, monkeypatch):
    """Factory: TestClient over a fresh app; env overrides per call.
    Reuses tmp_path, so two calls in one test share the same DB file
    (that is the restart-persistence scenario)."""

    def _make(**overrides):
        from fastapi.testclient import TestClient

        from triage.plugin.app import create_app

        env = {
            **BASE_ENV,
            "DB_PATH": str(tmp_path / "triage.db"),
            "MODEL_PATH": str(REAL_BUNDLE),
            **overrides,
        }
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        return TestClient(create_app())

    return _make
