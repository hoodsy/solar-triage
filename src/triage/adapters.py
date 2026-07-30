"""Source adapters: each turns a site's raw data into the canonical frame.

Canonical contract (every adapter's postcondition): tz-aware site-local
DatetimeIndex named "measured_on" at site.interval; column ac_power_kw (kW)
and, when the site has an irradiance stream, poa_wm2 (W/m^2). expected_kw is
a model, not a measurement — it is computed downstream in ingest, never here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol

import pandas as pd

if TYPE_CHECKING:
    from triage.config import SiteConfig


class Adapter(Protocol):
    def load(self, site: SiteConfig) -> pd.DataFrame:
        """Return the canonical measured frame for this site."""
        ...


@dataclass(frozen=True)
class SourceFile:
    name: str  # filename under the adapter's data_dir
    time_col: str = "measured_on"
    tz: str | None = None  # None: naive stamps in site-local time


@dataclass(frozen=True)
class Stream:
    files: tuple[SourceFile, ...]  # concat order = dedupe precedence order
    column: str  # source data column to extract
    keep: Literal["first", "last"] = "last"  # duplicate-timestamp winner
    resample: bool = False  # mean-resample to site.interval


@dataclass(frozen=True)
class CsvAdapter:
    data_dir: Path
    meter: Stream  # becomes ac_power_kw
    irradiance: Stream | None = None  # becomes poa_wm2; None = clear-sky site

    def _load_stream(self, stream: Stream, site: SiteConfig, name: str) -> pd.DataFrame:
        frames = []
        for f in stream.files:
            df = pd.read_csv(
                self.data_dir / f.name, parse_dates=[f.time_col], index_col=f.time_col
            )
            if f.tz is None:
                df.index = df.index.tz_localize(
                    site.tz,
                    ambiguous="NaT",  # fall-back hour recorded once: unresolvable
                    nonexistent="shift_forward",
                )
            else:
                df.index = df.index.tz_localize(f.tz).tz_convert(site.tz)
            df = df[df.index.notna()]
            df.index.name = "measured_on"
            frames.append(df)
        out = pd.concat(frames)
        out = out[~out.index.duplicated(keep=stream.keep)].sort_index()
        out = out[[stream.column]].rename(columns={stream.column: name})
        if stream.resample:
            out = out.resample(site.interval, closed="right", label="right").mean()
        return out

    def load(self, site: SiteConfig) -> pd.DataFrame:
        meter = self._load_stream(self.meter, site, "ac_power_kw")
        if self.irradiance is None:
            return meter
        poa = self._load_stream(self.irradiance, site, "poa_wm2")
        return meter.join(poa, how="outer")


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
