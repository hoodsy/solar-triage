"""Gate 2: day-close mechanics — feature parity with the batch path, the
streaming close-and-predict loop, and timezone discipline."""

from datetime import timedelta
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("fastapi")

from triage.config import SiteConfig  # noqa: E402
from triage.ingest.physics import clearsky_poa, expected_kw  # noqa: E402
from triage.plugin import dayclose, store  # noqa: E402
from triage.plugin.bundle import load_bundle  # noqa: E402
from triage.plugin.config import Settings  # noqa: E402
from triage.train.features import day_features  # noqa: E402

pytestmark = pytest.mark.skipif(
    not Path("model/model.joblib").exists(), reason="trained bundle not present"
)

TZ = "Pacific/Auckland"


def make_settings(tmp_path) -> Settings:
    site = SiteConfig(
        name="test node", tz=TZ, dc_capacity_kw=2.0, ac_capacity_kw=1.9,
        source=None, lat=-36.85, lon=174.76, tilt=25.0, azimuth=0.0,
    )
    return Settings(
        site=site, node_id=120, power_source_id="Solar",
        prediction_source_id="/triage/1", model_path=Path("model/model.joblib"),
        db_path=tmp_path / "triage.db", backfill_days=0, weather=False,
    )


def yesterday(tz=TZ):
    return (pd.Timestamp.now(tz=tz) - pd.Timedelta("1D")).date()


def day_grid(day, site):
    start = pd.Timestamp(day, tz=site.tz)
    return pd.date_range(start, start + pd.Timedelta("1D"), freq=site.interval,
                         inclusive="left")


def bell_kw(grid, site, scale=0.9):
    """A clean healthy day: the clear-sky expectation times a constant."""
    cs = clearsky_poa(grid, site)
    return expected_kw(cs, site) * scale


def flush_stamp(site) -> int:
    """The bucket-start stamp of TODAY's 00:00 label — yesterday's closing
    interval. Posting it both completes yesterday's grid and proves the
    stream has moved past it; today itself never closes."""
    midnight = pd.Timestamp.now(tz=site.tz).normalize()
    return int((midnight - pd.Timedelta(site.interval)).timestamp())


def test_feature_parity_with_batch_path(tmp_path):
    settings = make_settings(tmp_path)
    site = settings.site
    day = yesterday()
    grid = day_grid(day, site)
    cs = clearsky_poa(grid, site)
    ac = (expected_kw(cs, site) * 0.9).fillna(0.0)

    # batch frame: exactly what build_dataset makes for a clear-sky site
    df_batch = pd.DataFrame(
        {"ac_power_kw": ac, "expected_kw": expected_kw(cs, site),
         "clearsky_kw": expected_kw(cs, site)}
    )

    # plugin frame: the same day pushed through the datum store. The stored
    # timestamp is the bucket START = label − interval.
    conn = store.connect(settings.db_path)
    step = pd.Timedelta(site.interval)
    store.upsert_intervals(
        conn,
        [("Solar", int((ts - step).timestamp()), float(v) * 1000.0)
         for ts, v in ac.items()],
    )
    df_plugin = dayclose._intraday(day, settings, conn)

    pd.testing.assert_frame_equal(df_plugin[df_batch.columns], df_batch)

    # belt and braces: identical frames -> identical features, NaN-aware
    daily = pd.DataFrame(
        {"pi": 0.9, "pi_baseline": 1.0, "coverage": 1.0, "snow_cm": 0.0},
        index=pd.DatetimeIndex([pd.Timestamp(day, tz=site.tz)]),
    )
    day_ts = pd.Timestamp(day, tz=site.tz)
    f_batch = day_features(day_ts, df_batch, daily, site)
    f_plugin = day_features(day_ts, df_plugin, daily, site)
    assert set(f_batch) == set(f_plugin)
    for name in f_batch:
        assert f_batch[name] == pytest.approx(f_plugin[name], nan_ok=True, abs=0), name


def test_stream_close_predict_and_baseline(make_client):
    """Seven healthy days streamed day by day: each post closes the previous
    day and returns its prediction; the online baseline appears once five
    healthy days exist."""
    site = make_settings(Path(".")).site
    bundle = load_bundle(Path("model/model.joblib"))
    start = yesterday() - timedelta(days=6)

    seen = []
    with make_client() as client:
        for offset in range(7):
            day = start + timedelta(days=offset)
            grid = day_grid(day, site)
            ac = bell_kw(grid, site).fillna(0.0)
            step = pd.Timedelta(site.interval)
            datums = [
                {"nodeId": 120, "sourceId": "Solar",
                 "timestamp": int((ts - step).timestamp()),
                 "i": {"watts": float(v) * 1000.0}}
                for ts, v in ac.items()
            ]
            body = client.post("/measure", json={"datums": datums}).json()
            assert body["rejected"] == 0
            seen.extend(body["predictions"])

        # each day closed only once the next day's labels proved it complete
        assert client.get("/health").json()["details"]["closed_days"] == 6
        flush = {"nodeId": 120, "sourceId": "Solar",
                 "timestamp": flush_stamp(site), "i": {"watts": 0.0}}
        body = client.post("/measure", json={"datums": [flush]}).json()
        seen.extend(body["predictions"])
        details = client.get("/health").json()["details"]
        assert details["closed_days"] == 7

    assert len(seen) == 7
    for p in seen:
        assert p["nodeId"] == 120 and p["sourceId"] == "/triage/1"
        assert p["s"]["faultClass"] in bundle.classes
        assert set(p["meta"]) == {"confidence", "history_days", "model_version"}
        assert p["meta"]["model_version"] == bundle.version
    # a 0.9x-clear-sky bell with a healthy history is a healthy day
    assert [p["s"]["faultClass"] for p in seen[-2:]] == ["healthy", "healthy"]


def test_long_outage_holds_baseline_and_stays_outage(tmp_path):
    """The first replay's failure mode, pinned: healthy history, then dead
    days beyond the baseline window. The held baseline must keep pi_rel ~ 0
    and the label outage — never the healthy death-spiral."""
    settings = make_settings(tmp_path)
    site = settings.site
    bundle = load_bundle(settings.model_path)
    conn = store.connect(settings.db_path)
    step = pd.Timedelta(site.interval)

    start = yesterday() - timedelta(days=44)
    for offset in range(45):  # 10 healthy days, then a 35-day outage
        day = start + timedelta(days=offset)
        grid = day_grid(day, site)
        ac = bell_kw(grid, site).fillna(0.0)
        if offset >= 10:  # telemetry alive, plant dead
            ac = ac * 0.0
        store.upsert_intervals(
            conn,
            [("Solar", int((ts - step).timestamp()), float(v) * 1000.0)
             for ts, v in ac.items()],
        )
    store.upsert_intervals(conn, [("Solar", flush_stamp(site), 0.0)])
    dayclose.close_pending(settings, bundle, conn)

    rows = conn.execute(
        "SELECT date, label, pi_baseline FROM days ORDER BY date"
    ).fetchall()
    assert len(rows) == 45
    dead = rows[10:]
    assert all(label == "outage" for _, label, _ in dead), [r[1] for r in dead]
    # the baseline held at the healthy level through the whole outage
    held = {baseline for _, _, baseline in dead}
    assert all(b is not None and b > 0.5 for b in held), held


def test_utc_local_boundary_and_data_gap(tmp_path):
    """01:00 local in Auckland is 13:00 UTC the PREVIOUS day: the datum must
    close on its local date, and a one-interval day is a deterministic
    data_gap that never asks the model."""
    settings = make_settings(tmp_path)
    day = yesterday()
    local = pd.Timestamp(day, tz=TZ) + pd.Timedelta("1h")
    assert local.tz_convert("UTC").date() == day - timedelta(days=1)  # the trap is real

    conn = store.connect(settings.db_path)
    store.upsert_intervals(conn, [("Solar", int(local.timestamp()), 500.0)])
    bundle = load_bundle(settings.model_path)
    assert dayclose.close_pending(settings, bundle, conn) == 0  # nothing beyond it yet
    store.upsert_intervals(conn, [("Solar", flush_stamp(settings.site), 0.0)])
    closed = dayclose.close_pending(settings, bundle, conn)

    assert closed == 1
    rows = conn.execute("SELECT date, label, confidence, pi FROM days").fetchall()
    assert rows == [(str(day), "data_gap", 1.0, None)]
    (pred,) = store.drain_predictions(conn)
    assert pred["s"]["faultClass"] == "data_gap"
    end = pd.Timestamp(day, tz=TZ) + pd.Timedelta("1D")
    assert pred["timestamp"] == int(end.timestamp())


def test_night_fill_gives_daytime_only_stream_full_coverage(tmp_path):
    """A node that only reports lit intervals must not data_gap every day:
    sun-down absences are implicit zeros, exactly as in the batch build."""
    settings = make_settings(tmp_path)
    day = yesterday()
    grid = day_grid(day, settings.site)
    cs = clearsky_poa(grid, settings.site)
    ac = (expected_kw(cs, settings.site) * 0.9).fillna(0.0)
    lit = cs > 0

    conn = store.connect(settings.db_path)
    step = pd.Timedelta(settings.site.interval)
    store.upsert_intervals(
        conn,
        [("Solar", int((ts - step).timestamp()), float(v) * 1000.0)
         for ts, v in ac[lit].items()],
    )
    store.upsert_intervals(conn, [("Solar", flush_stamp(settings.site), 0.0)])
    bundle = load_bundle(settings.model_path)
    dayclose.close_pending(settings, bundle, conn)
    date, label, coverage = conn.execute(
        "SELECT date, label, coverage FROM days"
    ).fetchone()
    assert date == str(day)
    assert coverage == pytest.approx(1.0)
    assert label != "data_gap"


def test_partial_day_never_closes_early(tmp_path):
    """Production cadence: posts arrive every few minutes. A day with only
    its morning buffered must stay open — the second replay closed every
    day at its first hour before this rule was fixed."""
    settings = make_settings(tmp_path)
    site = settings.site
    day = yesterday()
    grid = day_grid(day, site)
    ac = bell_kw(grid, site).fillna(0.0)
    step = pd.Timedelta(site.interval)
    rows = [("Solar", int((ts - step).timestamp()), float(v) * 1000.0)
            for ts, v in ac.items()]

    conn = store.connect(settings.db_path)
    bundle = load_bundle(settings.model_path)
    store.upsert_intervals(conn, rows[:32])  # morning only
    assert dayclose.close_pending(settings, bundle, conn) == 0

    store.upsert_intervals(conn, rows[32:])
    store.upsert_intervals(conn, [("Solar", flush_stamp(site), 0.0)])
    assert dayclose.close_pending(settings, bundle, conn) == 1
    label, coverage = conn.execute("SELECT label, coverage FROM days").fetchone()
    assert coverage == pytest.approx(1.0)
    assert label != "data_gap"
