"""PVDAQ system 51, NREL x-Si 7 test array, Golden CO.
Twin of system 50: 6 kW DC, tilt 45 / azimuth 158, 15-min 1994-2023,
W-scale ac_power + POA + ambient °C, fixed MST, met join for snow."""

from pathlib import Path

from triage.adapters import LakeColumn, PvdaqLakeAdapter
from triage.config import SiteConfig
from triage.weather import OpenMeteoWeather

SITE = SiteConfig(
    name="PVDAQ 51 NREL x-Si 7",
    tz="Etc/GMT+7",
    dc_capacity_kw=6.0,
    ac_capacity_kw=6.5,  # empirical 15-min p99.9
    lat=39.7416,
    lon=-105.1734,
    tilt=45.0,
    azimuth=158.0,
    source=PvdaqLakeAdapter(
        data_dir=Path("data/51/lake"),
        meter=LakeColumn(773, scale=0.001),
        irradiance=LakeColumn(771),
        temperature=LakeColumn(780),
        start="1994-01-01",
    ),
    weather=OpenMeteoWeather(
        start="1994-01-01",
        end="2023-03-01",
        cache_dir=Path("data/51"),
    ),
)
