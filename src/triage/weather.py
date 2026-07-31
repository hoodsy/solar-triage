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

from triage.adapters import cached_csv

if TYPE_CHECKING:
    from triage.config import SiteConfig

OM_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


@dataclass(frozen=True)
class OpenMeteoWeather:
    start: str  # fixed local-date window, e.g. "2025-08-01"
    end: str
    cache_dir: Path | None = None

    def _cache_path(self, prefix: str, site: SiteConfig) -> Path | None:
        if self.cache_dir is None:
            return None
        return (
            self.cache_dir
            / f"{prefix}_{site.lat}_{site.lon}_{self.start}_{self.end}.csv"
        )

    def _get(self, site: SiteConfig, hourly_vars: str, **params) -> dict:
        resp = httpx.get(
            OM_ARCHIVE_URL,
            params={
                "latitude": site.lat,
                "longitude": site.lon,
                "start_date": self.start,
                "end_date": self.end,
                "hourly": hourly_vars,
                "timezone": "UTC",
                **params,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()["hourly"]

    def poa(self, site: SiteConfig) -> pd.Series:
        """Interval-ending POA series (W/m^2) on the site grid."""
        hourly = cached_csv(
            self._cache_path("openmeteo", site),
            site.tz,
            lambda: self._fetch(site).to_frame(),
        )["poa_wm2"]
        return self._upsample(hourly, site)

    def met(self, site: SiteConfig) -> pd.DataFrame:
        """Hourly met frame (temp_c, rain_mm, snow_cm) on the site clock;
        cached like poa. temp_c is the on-the-hour reading, rain_mm/snow_cm
        the preceding-hour sums. Cache prefix carries a v2: the column set
        grew snow_cm, and stale caches would silently lack it."""
        return cached_csv(
            self._cache_path("openmeteo_met2", site),
            site.tz,
            lambda: self._fetch_met(site),
        )

    def _index(self, data: dict, site: SiteConfig) -> pd.DatetimeIndex:
        # radiation values are the preceding-hour mean: labels are already
        # interval-ending, matching the canonical contract — no shift needed
        return (
            pd.DatetimeIndex(pd.to_datetime(data["time"]), name="measured_on")
            .tz_localize("UTC")
            .tz_convert(site.tz)
        )

    def _fetch(self, site: SiteConfig) -> pd.Series:
        data = self._get(
            site,
            "global_tilted_irradiance",
            tilt=site.tilt,
            # convention translation: pvlib azimuth is 0=north, Open-Meteo
            # is 0=south (verified empirically: the north-facing setting
            # collects 2.1x the winter energy at Auckland's latitude)
            azimuth=site.azimuth - 180,
        )
        return pd.Series(
            data["global_tilted_irradiance"],
            index=self._index(data, site),
            name="poa_wm2",
            dtype=float,
        )

    def _fetch_met(self, site: SiteConfig) -> pd.DataFrame:
        data = self._get(site, "temperature_2m,precipitation,snowfall")
        return pd.DataFrame(
            {
                "temp_c": data["temperature_2m"],
                "rain_mm": data["precipitation"],
                "snow_cm": data["snowfall"],
            },
            index=self._index(data, site),
            dtype=float,
        )

    @staticmethod
    def _upsample(
        hourly: pd.Series | pd.DataFrame, site: SiteConfig
    ) -> pd.Series | pd.DataFrame:
        """Hour-mean -> site.interval by backfill: each sub-interval inherits
        its hour's mean, preserving energy sums exactly (interpolation would
        smooth the shape but distort daily totals)."""
        steps = int(pd.Timedelta("1h") / pd.Timedelta(site.interval))
        if steps == 1:
            return hourly  # grids already match: nothing to do
        if steps < 1:
            raise NotImplementedError(
                "site interval coarser than hourly weather data — needs "
                "downsampling, which no site has required yet"
            )
        grid = pd.date_range(
            hourly.index[0] - pd.Timedelta("1h") + pd.Timedelta(site.interval),
            hourly.index[-1],
            freq=site.interval,
            name="measured_on",
        )
        return hourly.reindex(grid).bfill(limit=steps - 1)

    @staticmethod
    def _met_to_grid(met: pd.DataFrame, site: SiteConfig) -> pd.DataFrame:
        """Hourly met -> site.interval. temp is a level (bfill); rain and
        snow are sums (bfill / steps so daily totals survive resampling)."""
        steps = int(pd.Timedelta("1h") / pd.Timedelta(site.interval))
        out = OpenMeteoWeather._upsample(met, site)
        if steps > 1:
            sums = {
                c: out[c] / steps for c in ("rain_mm", "snow_cm") if c in out
            }
            out = out.assign(**sums)
        return out
