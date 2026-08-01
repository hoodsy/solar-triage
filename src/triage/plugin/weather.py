"""Per-day Open-Meteo fetch for day-close, reusing the batch OpenMeteoWeather.

Two edge-specific concerns the batch never has:

- A single LOCAL date spans two UTC dates (Auckland is UTC+12/+13), and the
  archive API buckets by UTC day — so each close fetches a 3-UTC-day window
  around the target date and lets the caller slice its local-day grid.
- Archive lag: ERA5 data for the last few days may come back all-null.
  cached_csv writes its cache unconditionally, which would freeze that empty
  answer forever — so an all-NaN result is treated as missing AND its cache
  file is removed, letting a later boot retry once the archive catches up.
"""

from __future__ import annotations

import logging
from datetime import date as Date
from datetime import timedelta
from pathlib import Path

import pandas as pd

from triage.config import SiteConfig
from triage.ingest.weather import OpenMeteoWeather

log = logging.getLogger("triage.plugin")


def day_weather(
    day: Date, site: SiteConfig, cache_dir: Path
) -> tuple[pd.Series | None, pd.DataFrame | None]:
    """(poa series, met frame) on the site clock for the local day, either
    of which is None when unavailable — the caller degrades gracefully."""
    om = OpenMeteoWeather(
        start=str(day - timedelta(days=1)),
        end=str(day + timedelta(days=1)),
        cache_dir=cache_dir,
    )
    poa = _fetch(lambda: om.poa(site), om._cache_path("openmeteo", site), "poa", day)
    met = _fetch(lambda: om.met(site), om._cache_path("openmeteo_met2", site), "met", day)
    return poa, (om._met_to_grid(met, site) if met is not None else None)


def _fetch(load, cache_path: Path | None, what: str, day: Date):
    try:
        data = load()
    except Exception:
        log.warning("open-meteo %s fetch failed for %s; degrading", what, day, exc_info=True)
        return None
    empty = bool(
        data.isna().all().all() if isinstance(data, pd.DataFrame) else data.isna().all()
    )
    if empty:
        # archive hasn't caught up; drop the cache so a later close retries
        if cache_path is not None:
            Path(cache_path).unlink(missing_ok=True)
        log.info("open-meteo %s empty for %s (archive lag); degrading", what, day)
        return None
    return data
