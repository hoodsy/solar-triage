"""Solar physics models — the only module that knows watts, suns, and derates.

Everything here is a pure function of irradiance, geometry, and site facts;
no frame plumbing, no I/O.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

    from triage.config import SiteConfig


def expected_kw(poa_wm2: pd.Series, site: SiteConfig) -> pd.Series:
    """Expected AC power: nameplate scaled by "suns" (POA / 1000 W/m^2),
    derated for the loss stack (heat, inverter, wiring, mismatch, aging)."""
    return site.dc_capacity_kw * (poa_wm2 / 1000.0) * site.derate


def clearsky_poa(index: pd.DatetimeIndex, site: SiteConfig) -> pd.Series:
    """Clear-sky plane-of-array irradiance for sites without a POA sensor.

    This is a *ceiling*, not a forecast: unlike measured POA, clouds do not
    cancel out of PI for clear-sky sites, so their PI is weather-noisy and
    flag thresholds need per-site retuning.
    """
    import pvlib  # imported lazily: measured-POA sites never pay for it

    location = pvlib.location.Location(site.lat, site.lon, tz=site.tz)
    solpos = location.get_solarposition(index)
    clearsky = location.get_clearsky(index)
    total = pvlib.irradiance.get_total_irradiance(
        surface_tilt=site.tilt,
        surface_azimuth=site.azimuth,
        solar_zenith=solpos["apparent_zenith"],
        solar_azimuth=solpos["azimuth"],
        dni=clearsky["dni"],
        ghi=clearsky["ghi"],
        dhi=clearsky["dhi"],
    )
    return total["poa_global"]
