"""PVDAQ system 1318, St. Petersburg Parks - Crescent Lake Park MB, FL.
A ~1 kW micro-site (rtw p99.9 896 W early era) that collapses to 25%
capacity from 2016 — kept precisely for that degradation story. Same
15-second rtw format as 1325; meter-only, Open-Meteo tier, DST-aware
Eastern."""

from pathlib import Path

from triage.ingest import LakeColumn, PvdaqLakeAdapter
from triage.config import SiteConfig
from triage.ingest.weather import OpenMeteoWeather

SITE = SiteConfig(
    name="PVDAQ 1318 Crescent Lake",
    tz="America/New_York",
    dc_capacity_kw=1.1,
    ac_capacity_kw=0.9,  # early-era empirical ceiling
    lat=27.7883,
    lon=-82.6414,
    tilt=10.0,
    azimuth=180.0,
    source=PvdaqLakeAdapter(
        data_dir=Path("data/1318/lake"),
        meter=LakeColumn(271, scale=0.001),  # rtw, W
    ),
    weather=OpenMeteoWeather(
        start="2013-03-18",
        end="2017-07-08",
        cache_dir=Path("data/1318"),
    ),
)
