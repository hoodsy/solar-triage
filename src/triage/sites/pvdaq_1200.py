"""PVDAQ system 1200, "Distributed Sun - BWI Hilton", Linthicum Heights
MD. 51.8 kW DC at tilt 10 / azimuth 205. The census undersold it — 39
channels including a 2010-2013 sub-metered era — but the usable clean
span is channel 4197 alone: kW-scale from 2013-11, W-scale after the
fleet-wide 2018-08-04 logger flip (clean break, zero overlap), through
2020-07. The older meter channels (2751/2752) and the six inverter
channels die in 2013 and are left out. Stamps are DST-aware local
(June peak 13, December 12), unlike fixed-EST 1199/1202. No irradiance
— Open-Meteo tier."""

from pathlib import Path

from triage.adapters import LakeColumn, PvdaqLakeAdapter
from triage.config import SiteConfig
from triage.weather import OpenMeteoWeather

SITE = SiteConfig(
    name="PVDAQ 1200 BWI Hilton",
    tz="America/New_York",
    dc_capacity_kw=51.84,
    ac_capacity_kw=46.0,  # empirical converted 15-min p99.9
    lat=39.1958,
    lon=-76.6808,
    tilt=10.0,
    azimuth=205.0,
    source=PvdaqLakeAdapter(
        data_dir=Path("data/1200/lake"),
        meter=LakeColumn(4197, scale=1.0, breaks=(("2018-08-04", 0.0, 0.001),)),
    ),
    weather=OpenMeteoWeather(
        start="2013-11-29",
        end="2020-07-27",
        cache_dir=Path("data/1200"),
    ),
)
