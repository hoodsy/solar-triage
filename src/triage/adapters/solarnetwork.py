from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import pandas as pd

if TYPE_CHECKING:
    from triage.config import SiteConfig

SN_DATUM_URL = "https://data.solarnetwork.net/solarquery/api/v1/pub/datum/list"
SN_AGGREGATION = {"15min": "FifteenMinute", "1h": "Hour"}


@dataclass(frozen=True)
class SolarNetworkAdapter:
    """Polled-batch loader for a public SolarNetwork node.

    Two window modes: a trailing `lookback_days` window ("streaming" for a
    daily triage pipeline), or a fixed `start`/`end` study window. Fixed
    windows are stable, so they are cached to disk (`cache_dir`) on first
    fetch — later runs read the local copy and never touch the API.
    """

    node_id: int
    power_source_id: str  # e.g. "Solar" on node 120
    lookback_days: int = 60  # trailing window when start/end unset
    start: str | None = None  # fixed local-date window, e.g. "2025-08-01"
    end: str | None = None
    cache_dir: Path | None = None  # only fixed windows are cached

    def load(self, site: SiteConfig) -> pd.DataFrame:
        fixed = self.start is not None and self.end is not None
        if fixed:
            w_start = pd.Timestamp(self.start, tz=site.tz)
            w_end = pd.Timestamp(self.end, tz=site.tz)
        else:
            w_end = pd.Timestamp.now(tz=site.tz)
            w_start = w_end - pd.Timedelta(days=self.lookback_days)

        cache = None
        if self.cache_dir is not None and fixed:
            source_tag = self.power_source_id.replace("/", "_")
            cache = (
                self.cache_dir
                / f"node{self.node_id}_{source_tag}_{self.start}_{self.end}.csv"
            )
            if cache.exists():
                out = pd.read_csv(
                    cache, parse_dates=["measured_on"], index_col="measured_on"
                )
                out.index = out.index.tz_convert(site.tz)
                return out

        out = self._fetch(w_start, w_end, site)
        if cache is not None:
            cache.parent.mkdir(parents=True, exist_ok=True)
            out.tz_convert("UTC").to_csv(cache)  # store UTC: unambiguous on disk
        return out

    def _fetch(
        self, w_start: pd.Timestamp, w_end: pd.Timestamp, site: SiteConfig
    ) -> pd.DataFrame:
        rows: list[dict] = []
        # two measured API behaviors shape this loop: startDate/endDate are
        # interpreted as UTC (not node-local), and sub-hour aggregation
        # silently degrades to hourly beyond ~7 days -> fetch in 7d chunks
        chunk_start = w_start
        while chunk_start < w_end:
            chunk_end = min(chunk_start + pd.Timedelta(days=7), w_end)
            params = {
                "nodeId": self.node_id,
                "sourceIds": self.power_source_id,
                "startDate": chunk_start.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M"),
                "endDate": chunk_end.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M"),
                "aggregation": SN_AGGREGATION[site.interval],
                "max": 1000,
            }
            offset = 0
            throttled = 0
            while True:
                resp = httpx.get(
                    SN_DATUM_URL, params={**params, "offset": offset}, timeout=30.0
                )
                if resp.status_code == 429:  # rate-limited: back off and retry
                    throttled += 1
                    if throttled > 5:
                        resp.raise_for_status()
                    time.sleep(float(resp.headers.get("Retry-After", 10)))
                    continue
                resp.raise_for_status()
                data = resp.json()["data"]
                rows.extend(data["results"])
                offset += data["returnedResultCount"]
                if offset >= data["totalResults"] or data["returnedResultCount"] == 0:
                    break
            chunk_start = chunk_end
            time.sleep(0.5)  # pace chunk requests: this is a public API
        if not rows:
            raise ValueError(
                f"SolarNetwork node {self.node_id} source {self.power_source_id!r} "
                f"returned no datums for {w_start:%Y-%m-%d} -> {w_end:%Y-%m-%d}"
            )
        raw = pd.DataFrame(rows)
        index = pd.DatetimeIndex(
            pd.to_datetime(raw["created"], utc=True), name="measured_on"
        ).tz_convert(site.tz)
        # datum stamps mark the bucket START; the canonical contract labels
        # intervals by their END (matching the 2107 meter files and
        # Open-Meteo's preceding-hour convention) -> shift one interval
        index = index + pd.Timedelta(site.interval)
        out = pd.DataFrame(
            {"ac_power_kw": (raw["watts"] / 1000.0).to_numpy()}, index=index
        )
        return out[~out.index.duplicated(keep="last")].sort_index()
