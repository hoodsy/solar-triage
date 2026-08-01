"""Gate 1: /measure ingest semantics, persistence, and boot backfill."""

from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("fastapi")

from triage.plugin import backfill as backfill_mod  # noqa: E402

pytestmark = pytest.mark.skipif(
    not Path("model/model.joblib").exists(), reason="trained bundle not present"
)


def datum(ts, watts=None, source="Solar"):
    d = {"nodeId": 120, "sourceId": source, "timestamp": ts}
    if watts is not None:
        d["i"] = {"watts": watts}
    return d


def today_ts() -> int:
    """00:01 TODAY in site-local time: ingested but never day-closed (today
    is not fully past), so ingest counting stays isolated from Gate 2."""
    midnight = pd.Timestamp.now(tz="Pacific/Auckland").normalize()
    return int(midnight.timestamp()) + 60


def test_measure_counts_and_persistence(make_client):
    t0 = today_ts()
    batch = {
        "datums": [
            datum(t0, 410.0),
            datum(t0 + 900, 395.5),
            datum(t0, 300.0, source="House"),  # other stream: accepted, ignored
            {"sourceId": "Solar", "timestamp": t0 + 100},  # no nodeId -> rejected
            datum(t0 + 200),  # matching source, no watts -> rejected
            datum("not-a-ts", 5.0),  # bad timestamp -> rejected
        ]
    }
    with make_client() as client:
        r = client.post("/measure", json=batch)
        assert r.status_code == 200
        body = r.json()
        assert body["accepted"] == 3 and body["rejected"] == 3
        assert body["predictions"] == []
        assert client.get("/health").json()["details"]["buffered_intervals"] == 2

        # duplicate ts replaces, never double-counts
        client.post("/measure", json={"datums": [datum(t0, 999.0)]})
        assert client.get("/health").json()["details"]["buffered_intervals"] == 2

    # restart on the same DB file: rows survive
    with make_client() as client:
        assert client.get("/health").json()["details"]["buffered_intervals"] == 2


def test_body_garbage_is_spec_400(make_client):
    with make_client() as client:
        r = client.post("/measure", json={"nope": 1})
        assert r.status_code == 400
        assert "error" in r.json() and "message" in r.json()


class StubAdapter:
    calls = 0

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def load(self, site):
        StubAdapter.calls += 1
        # END-labeled local stamps, like the real adapter's canonical frame
        idx = pd.date_range("2026-07-01 06:15", periods=8, freq="15min", tz=site.tz)
        kw = [0.0, 0.4, 0.9, 1.2, 1.3, 1.1, 0.6, 0.1]
        return pd.DataFrame({"ac_power_kw": kw}, index=idx)


class FailingAdapter:
    def __init__(self, **kwargs):
        pass

    def load(self, site):
        raise ConnectionError("solarnetwork unreachable")


def test_backfill_populates_and_is_idempotent(make_client, monkeypatch):
    StubAdapter.calls = 0
    monkeypatch.setattr(backfill_mod, "SolarNetworkAdapter", StubAdapter)
    with make_client(BACKFILL_DAYS="30") as client:
        assert client.get("/health").json()["details"]["buffered_intervals"] == 8
    # double boot on the same DB: upsert, not append
    with make_client(BACKFILL_DAYS="30") as client:
        assert client.get("/health").json()["details"]["buffered_intervals"] == 8
    assert StubAdapter.calls == 2


def test_backfill_failure_still_boots(make_client, monkeypatch):
    monkeypatch.setattr(backfill_mod, "SolarNetworkAdapter", FailingAdapter)
    with make_client(BACKFILL_DAYS="30") as client:
        assert client.get("/health").json()["status"] == "healthy"
