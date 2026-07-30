from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from triage.config import SiteConfig

SN_DATUM_URL = "https://data.solarnetwork.net/solarquery/api/v1/pub/datum/list"
SN_AGGREGATION = {"15min": "FifteenMinute", "1h": "Hour"}


@dataclass(frozen=True)
class SolarNetworkAdapter:
    """Polled-batch loader for a public SolarNetwork node: each run fetches a
    trailing window of aggregated datums over HTTP ("streaming" for a daily
    triage pipeline). Datum timestamps arrive UTC; `watts` is the bucket mean.
    """

    node_id: int
    power_source_id: str  # e.g. "DB" on node 108 = combined PV output
    lookback_days: int = 60

    def load(self, site: SiteConfig) -> pd.DataFrame:
        import httpx  # lazy: CSV sites never pay for it

        end = pd.Timestamp.now(tz=site.tz)
        start = end - pd.Timedelta(days=self.lookback_days)
        rows: list[dict] = []
        # the API silently degrades sub-hour aggregation to hourly beyond ~7
        # days (measured: 7d -> 15-min, 14d -> hourly), so fetch in 7d chunks
        chunk_start = start
        while chunk_start < end:
            chunk_end = min(chunk_start + pd.Timedelta(days=7), end)
            params = {
                "nodeId": self.node_id,
                "sourceIds": self.power_source_id,
                "startDate": chunk_start.strftime("%Y-%m-%dT%H:%M"),
                "endDate": chunk_end.strftime("%Y-%m-%dT%H:%M"),
                "aggregation": SN_AGGREGATION[site.interval],
                "max": 1000,
            }
            offset = 0
            while True:
                resp = httpx.get(
                    SN_DATUM_URL, params={**params, "offset": offset}, timeout=30.0
                )
                resp.raise_for_status()
                data = resp.json()["data"]
                rows.extend(data["results"])
                offset += data["returnedResultCount"]
                if offset >= data["totalResults"] or data["returnedResultCount"] == 0:
                    break
            chunk_start = chunk_end
        if not rows:
            raise ValueError(
                f"SolarNetwork node {self.node_id} source {self.power_source_id!r} "
                f"returned no datums for the last {self.lookback_days} days"
            )
        raw = pd.DataFrame(rows)
        index = pd.DatetimeIndex(
            pd.to_datetime(raw["created"], utc=True), name="measured_on"
        ).tz_convert(site.tz)
        out = pd.DataFrame(
            {"ac_power_kw": (raw["watts"] / 1000.0).to_numpy()}, index=index
        )
        return out[~out.index.duplicated(keep="last")].sort_index()
