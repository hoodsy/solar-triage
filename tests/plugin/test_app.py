"""Gate 0: boot against the real bundle; /health per the plugin spec."""

from pathlib import Path

import joblib
import pytest

pytest.importorskip("fastapi")

pytestmark = pytest.mark.skipif(
    not Path("model/model.joblib").exists(), reason="trained bundle not present"
)


def test_boot_and_health(make_client):
    with make_client() as client:
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "healthy"
        assert isinstance(body["timestamp"], int)
        assert body["uptime"] >= 0
        details = body["details"]
        assert details["closed_days"] == 0
        assert details["buffered_intervals"] == 0
        assert details["model_version"]


def test_missing_env_fails_boot(make_client, monkeypatch):
    client = make_client()  # sets the full env; lifespan runs on enter, not here
    monkeypatch.delenv("SITE_TZ")
    with pytest.raises(RuntimeError, match="SITE_TZ"):
        with client:
            pass


def test_stale_bundle_fails_boot(make_client, tmp_path):
    # a pre-Gate-0 artifact ({model, features} only) must refuse to serve
    old = joblib.load("model/model.joblib")
    stale = tmp_path / "stale.joblib"
    joblib.dump({"model": old["model"], "features": old["features"]}, stale)
    with pytest.raises(RuntimeError, match="lacks"):
        with make_client(MODEL_PATH=str(stale)):
            pass
