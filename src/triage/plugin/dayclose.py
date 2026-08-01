"""Day-close: turn buffered intervals into closed days and prediction datums.

Grid and label conventions mirror the batch pipeline exactly, so
day_features sees the same frame either way — a local day is the 96
END-labeled site.interval stamps carrying that date (the 00:00 stamp is the
previous day's closing interval, just as in the batch frames), sourced from
posted timestamps in [midnight − interval, next midnight − interval). The
feature-parity test in tests/plugin/test_dayclose.py holds this contract.

One deliberate deviation from the batch trust ladder: expected power uses
weather POA where present and falls back to clear-sky PER INTERVAL
(combine_first) instead of per frame. Batch windows end deep in the past
where the archive is complete; the edge closes yesterday, where archive lag
would otherwise turn a fully-measured day into a fake data_gap.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from datetime import date as Date
from datetime import timedelta

import pandas as pd

from triage.ingest.build import build_daily
from triage.ingest.physics import clearsky_poa, expected_kw
from triage.plugin import constants, store
from triage.plugin.bundle import Bundle
from triage.plugin.config import Settings
from triage.plugin.weather import day_weather
from triage.train.features import day_features

log = logging.getLogger("triage.plugin")

BASELINE_WINDOW = 30  # closed days considered
BASELINE_MIN = 5  # healthy days required, else baseline is NaN


def close_pending(settings: Settings, bundle: Bundle, conn: sqlite3.Connection) -> int:
    """Close every fully-past local date that has no days row; returns how
    many days were closed. Runs at boot (after backfill) and on each
    /measure, so predictions queue as soon as a day becomes closeable."""
    closed = 0
    for day in _pending_dates(settings, conn):
        _close_day(day, settings, bundle, conn)
        closed += 1
    return closed


def _pending_dates(settings: Settings, conn: sqlite3.Connection) -> list[Date]:
    """Local dates ready to close: from the first buffered interval's LABEL
    date (a stamp at 23:45 belongs to the next day's 00:00 label) up to the
    last one's — a day only closes once data at or beyond it proves the
    stream has moved past, so interior gaps close as data_gap but the day a
    silent node will eventually report stays open. Never past yesterday.
    Bounding by the actual data span (not the calendar) is what lets the
    Gate 3 replay stream a months-old window through unchanged."""
    lo, hi = conn.execute(
        "SELECT MIN(ts), MAX(ts) FROM intervals WHERE source_id = ?",
        (settings.power_source_id,),
    ).fetchone()
    if lo is None:
        return []
    tz = settings.site.tz
    step = pd.Timedelta(settings.site.interval)
    today = pd.Timestamp.now(tz=tz).date()
    start = (pd.Timestamp(lo, unit="s", tz="UTC").tz_convert(tz) + step).date()
    last = (pd.Timestamp(hi, unit="s", tz="UTC").tz_convert(tz) + step).date()
    end = min(last, today - timedelta(days=1))
    have = {row[0] for row in conn.execute("SELECT date FROM days")}
    day, out = start, []
    while day <= end:
        if str(day) not in have:
            out.append(day)
        day += timedelta(days=1)
    return out


def _intraday(day: Date, settings: Settings, conn: sqlite3.Connection) -> pd.DataFrame:
    site = settings.site
    step = pd.Timedelta(site.interval)
    day_start = pd.Timestamp(day, tz=site.tz)
    day_end = day_start + pd.Timedelta("1D")
    grid = pd.date_range(day_start, day_end, freq=site.interval, inclusive="left")

    rows = conn.execute(
        "SELECT ts, watts FROM intervals WHERE source_id = ? AND ts >= ? AND ts < ?",
        (
            settings.power_source_id,
            int((day_start - step).timestamp()),
            int((day_end - step).timestamp()),
        ),
    ).fetchall()
    if rows:
        stamps = pd.to_datetime([ts for ts, _ in rows], unit="s", utc=True).tz_convert(
            site.tz
        )
        posted = pd.Series([w / 1000.0 for _, w in rows], index=stamps)
        # posted stamps mark the measurement instant / bucket start; the
        # [left, right)-bucket mean with a right label lands each one on the
        # canonical END-of-interval grid
        ac = (
            posted.resample(site.interval, closed="left", label="right")
            .mean()
            .reindex(grid)
        )
    else:
        ac = pd.Series(float("nan"), index=grid)

    cs_poa = clearsky_poa(grid, site)
    # implicit night zero, same rule as batch: sun-down absence is a zero,
    # daytime absence stays NaN and counts against coverage
    night = cs_poa <= 0
    ac = ac.where(~(night & ac.isna()), 0.0)

    df = pd.DataFrame({"ac_power_kw": ac})
    poa = cs_poa
    if settings.weather:
        w_poa, met = day_weather(day, site, settings.db_path.parent / "weather")
        if w_poa is not None:
            poa = w_poa.reindex(grid).combine_first(cs_poa)
        if met is not None:
            df = df.join(met.reindex(grid))
    df["expected_kw"] = expected_kw(poa, site)
    df["clearsky_kw"] = expected_kw(cs_poa, site)
    return df


def _baseline(conn: sqlite3.Connection) -> tuple[float, int]:
    """(trailing healthy-median pi, closed-day count) — the online stand-in
    for the batch fixpoint baseline; skew measured in the Gate 3 replay."""
    history = conn.execute(
        f"SELECT pi, label FROM days ORDER BY date DESC LIMIT {BASELINE_WINDOW}"
    ).fetchall()
    healthy = [pi for pi, label in history if label == "healthy" and pi is not None]
    n_closed = conn.execute("SELECT COUNT(*) FROM days").fetchone()[0]
    if len(healthy) < BASELINE_MIN:
        return float("nan"), n_closed
    return float(pd.Series(healthy).median()), n_closed


def _close_day(
    day: Date, settings: Settings, bundle: Bundle, conn: sqlite3.Connection
) -> None:
    site = settings.site
    df = _intraday(day, settings, conn)
    daily = build_daily(df, site)
    row = daily.iloc[0]
    coverage = float(row["coverage"])
    rain = float(row["rain_mm"]) if "rain_mm" in daily.columns else float("nan")
    snow = float(row["snow_cm"]) if "snow_cm" in daily.columns else float("nan")

    if coverage < site.coverage_min:
        # the model never trained on unseeable days; don't ask it about them
        _record(day, settings, conn, row, coverage, rain, snow,
                pi=None, baseline=None, label="data_gap", confidence=1.0,
                history_days=store.closed_days(conn), model_version=bundle.version)
        return

    pi = float(row["pi"])
    baseline, history_days = _baseline(conn)

    day_ts = pd.Timestamp(day, tz=site.tz)
    hist = pd.read_sql_query(
        "SELECT date, pi, pi_baseline, snow_cm FROM days ORDER BY date", conn
    )
    # SQL NULLs (data_gap days) arrive as None in object columns; the
    # feature math needs float-NaN columns
    numeric = {c: pd.to_numeric(hist[c], errors="coerce") for c in
               ("pi", "pi_baseline", "snow_cm")}
    daily_hist = pd.DataFrame(
        {
            "pi": list(numeric["pi"]) + [pi],
            "pi_baseline": list(numeric["pi_baseline"]) + [baseline],
            "snow_cm": list(numeric["snow_cm"]) + [snow],
        },
        index=pd.DatetimeIndex(
            list(pd.to_datetime(hist["date"]).dt.tz_localize(site.tz)) + [day_ts]
        ),
    )

    features = day_features(day_ts, df, daily_hist, site)
    values = {**features, "pi": pi, "coverage": coverage, "rain_mm": rain}
    X = pd.DataFrame([[values[f] for f in bundle.features]], columns=bundle.features)
    proba = bundle.model.predict_proba(X.astype(float))[0]
    label = str(bundle.model.classes_[proba.argmax()])
    _record(day, settings, conn, row, coverage, rain, snow,
            pi=pi, baseline=baseline, label=label,
            confidence=float(proba.max()), history_days=history_days,
            model_version=bundle.version)


def _record(
    day, settings, conn, row, coverage, rain, snow,
    *, pi, baseline, label, confidence, history_days, model_version,
) -> None:
    site = settings.site
    day_end = pd.Timestamp(day, tz=site.tz) + pd.Timedelta("1D")
    conn.execute(
        "INSERT INTO days (date, actual_kwh, expected_kwh, coverage, pi, "
        "pi_baseline, rain_mm, snow_cm, label, confidence, closed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            str(day),
            _sql(row["actual_kwh"]),
            _sql(row["expected_kwh"]),
            coverage,
            _sql(pi),
            _sql(baseline),
            _sql(rain),
            _sql(snow),
            label,
            confidence,
            int(time.time()),
        ),
    )
    store.queue_prediction(
        conn,
        {
            "nodeId": settings.node_id,
            "sourceId": settings.prediction_source_id,
            "timestamp": int(day_end.timestamp()),
            "s": {constants.FAULT_CLASS_KEY: label},
            "meta": {
                constants.META_CONFIDENCE: round(confidence, 4),
                constants.META_HISTORY_DAYS: history_days,
                constants.META_MODEL_VERSION: model_version,
            },
        },
    )
    log.info("closed %s: label=%s confidence=%.3f coverage=%.2f", day, label, confidence, coverage)


def _sql(value) -> float | None:
    """NaN -> NULL at the DB boundary."""
    if value is None:
        return None
    value = float(value)
    return None if value != value else value
