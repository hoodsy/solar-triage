"""Boot backfill: pull the trailing window from the SolarNetwork API so the
first closed day already has a baseline, instead of two weeks of NaN pi_rel.

Convention boundary, deliberate: the adapter returns the canonical frame
(kW, tz-aware local, END-of-interval labels); the store holds exactly what a
live node would POST (unix seconds at bucket START, watts). The shift and
scale are undone here so the two ingest paths meet in one representation.

Backfill failure is a warning, not a crash — the plugin then cold-starts on
/measure data alone, and features degrade to NaN until history accrues.
"""

from __future__ import annotations

import logging
import sqlite3

import pandas as pd

from triage.ingest.solarnetwork import SolarNetworkAdapter
from triage.plugin import store
from triage.plugin.config import Settings

log = logging.getLogger("triage.plugin")


def backfill(settings: Settings, conn: sqlite3.Connection) -> int:
    """Fetch the trailing window and upsert it; returns rows stored."""
    if settings.backfill_days <= 0:
        return 0
    adapter = SolarNetworkAdapter(
        node_id=settings.node_id,
        power_source_id=settings.power_source_id,
        lookback_days=settings.backfill_days,
    )
    try:
        df = adapter.load(settings.site)
    except Exception:
        log.warning(
            "backfill failed for node %s; cold-starting on /measure data only",
            settings.node_id,
            exc_info=True,
        )
        return 0
    step = pd.Timedelta(settings.site.interval)
    rows = [
        (settings.power_source_id, int((ts - step).timestamp()), float(kw) * 1000.0)
        for ts, kw in df["ac_power_kw"].dropna().items()
    ]
    store.upsert_intervals(conn, rows)
    log.info("backfilled %d intervals (%d days requested)", len(rows), settings.backfill_days)
    return len(rows)
