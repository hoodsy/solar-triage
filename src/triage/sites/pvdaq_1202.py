"""PVDAQ system 1202, "Distributed Sun - 6 Executive Campus", Cherry
Hill NJ. 51.8 kW DC roof, azimuth 230 (southwest — the power peak stamps
~1h after solar noon in BOTH seasons, consistent with fixed EST stamps
like 1199). 6 sub-metered inverters on a sparser reporting grid than the
meter. The "_kw"-named meter channel is actually W-scale (42,240 raw on
a 51.8 kW plant); the ambient_temp_k channel has 3% coverage — skipped.
No irradiance — Open-Meteo tier."""

from pathlib import Path

from triage.adapters import LakeColumn, PvdaqLakeAdapter
from triage.config import SiteConfig
from triage.weather import OpenMeteoWeather

SITE = SiteConfig(
    name="PVDAQ 1202 Cherry Hill",
    tz="Etc/GMT+5",
    dc_capacity_kw=51.84,
    ac_capacity_kw=41.2,  # empirical 15-min p99.9 (41,183 W)
    n_units=6,  # 6 x ~7.7 kW string inverters
    lat=39.9292,
    lon=-75.0472,
    tilt=10.0,
    azimuth=230.0,
    electrical=("2810", "2815", "2820", "2825", "2830", "2835"),
    source=PvdaqLakeAdapter(
        data_dir=Path("data/1202/lake"),
        meter=LakeColumn(2802, scale=0.001),  # ac_power_metered_kw: W despite the name
        inverter_scale=0.001,
    ),
    weather=OpenMeteoWeather(
        start="2010-12-29",
        end="2020-07-27",
        cache_dir=Path("data/1202"),
    ),
)
