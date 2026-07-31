"""PVDAQ system 1325, St. Petersburg Parks - Campbell Park Rec Center, FL.
~34 kW DC (census blank; sized from the early-era 30 kW ceiling),
meter-only at 15-SECOND cadence (rtw = real-time watts), 2013-2018.
The ceiling slides 30 -> 20 kW across the span — real capacity decline.
DST-aware Eastern stamps; geometry a Florida-roof guess; Open-Meteo
tier."""

from pathlib import Path

from triage.adapters import LakeColumn, PvdaqLakeAdapter
from triage.config import SiteConfig
from triage.weather import OpenMeteoWeather

SITE = SiteConfig(
    name="PVDAQ 1325 Campbell Park",
    tz="America/New_York",
    dc_capacity_kw=34.0,
    ac_capacity_kw=30.0,  # early-era empirical ceiling
    lat=27.7643,
    lon=-82.6497,
    tilt=10.0,
    azimuth=180.0,
    source=PvdaqLakeAdapter(
        data_dir=Path("data/1325/lake"),
        meter=LakeColumn(280, scale=0.001),  # rtw, W
    ),
    weather=OpenMeteoWeather(
        start="2013-03-18",
        end="2018-07-08",
        cache_dir=Path("data/1325"),
    ),
)
