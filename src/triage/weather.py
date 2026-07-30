"""Weather-derived plane-of-array irradiance for sites without a POA sensor.

Source: Open-Meteo's historical archive (ERA5 blend), which computes tilted
irradiance server-side from reanalysis weather. Trust tier: reliable at DAILY
aggregation (~10-15% error), noisy hour-to-hour — daily PI is the number to
believe; intraday shape rules should lean on it lightly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import pandas as pd

if TYPE_CHECKING:
    from triage.config import SiteConfig

OM_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


@dataclass(frozen=True)
class OpenMeteoWeather:
    start: str  # fixed local-date window, e.g. "2025-08-01"
    end: str
    cache_dir: Path | None = None

    def poa(self, site: SiteConfig) -> pd.Series:
        """Interval-ending POA series (W/m^2) on the site grid."""
        cache = None
        if self.cache_dir is not None:
            cache = (
                self.cache_dir
                / f"openmeteo_{site.lat}_{site.lon}_{self.start}_{self.end}.csv"
            )
            if cache.exists():
                hourly = pd.read_csv(
                    cache, parse_dates=["measured_on"], index_col="measured_on"
                )["poa_wm2"]
                hourly.index = hourly.index.tz_convert(site.tz)
                return self._upsample(hourly, site)

        hourly = self._fetch(site)
        if cache is not None:
            cache.parent.mkdir(parents=True, exist_ok=True)
            hourly.tz_convert("UTC").to_frame().to_csv(cache)  # UTC on disk
        return self._upsample(hourly, site)

    def _fetch(self, site: SiteConfig) -> pd.Series:
        resp = httpx.get(
            OM_ARCHIVE_URL,
            params={
                "latitude": site.lat,
                "longitude": site.lon,
                "start_date": self.start,
                "end_date": self.end,
                "hourly": "global_tilted_irradiance",
                "tilt": site.tilt,
                # convention translation: pvlib azimuth is 0=north, Open-Meteo
                # is 0=south (verified empirically: the north-facing setting
                # collects 2.1x the winter energy at Auckland's latitude)
                "azimuth": site.azimuth - 180,
                "timezone": "UTC",
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()["hourly"]
        # radiation values are the preceding-hour mean: labels are already
        # interval-ending, matching the canonical contract — no shift needed
        index = (
            pd.DatetimeIndex(pd.to_datetime(data["time"]), name="measured_on")
            .tz_localize("UTC")
            .tz_convert(site.tz)
        )
        return pd.Series(
            data["global_tilted_irradiance"], index=index, name="poa_wm2", dtype=float
        )

    @staticmethod
    def _upsample(hourly: pd.Series, site: SiteConfig) -> pd.Series:
        """Hour-mean -> site.interval by backfill: each sub-interval inherits
        its hour's mean, preserving energy sums exactly (interpolation would
        smooth the shape but distort daily totals)."""
        steps = int(pd.Timedelta("1h") / pd.Timedelta(site.interval))
        if steps <= 1:
            return hourly
        grid = pd.date_range(
            hourly.index[0] - pd.Timedelta("1h") + pd.Timedelta(site.interval),
            hourly.index[-1],
            freq=site.interval,
            name="measured_on",
        )
        return hourly.reindex(grid).bfill(limit=steps - 1)
