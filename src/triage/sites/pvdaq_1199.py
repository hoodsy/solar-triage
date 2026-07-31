"""PVDAQ system 1199, "Distributed Sun - Hunt Valley", Cockeysville MD.
52.9 kW DC roof, 7 sub-metered inverters, 2010-2020. No on-site
irradiance or met sensors — expected power rides Open-Meteo reanalysis.
Stamps are FIXED EST year-round (June and December both peak at stamp
hour 12; DST-aware stamps would put June at 13), hence Etc/GMT+5."""

from pathlib import Path

from triage.adapters import LakeColumn, PvdaqLakeAdapter
from triage.config import SiteConfig
from triage.weather import OpenMeteoWeather

SITE = SiteConfig(
    name="PVDAQ 1199 Hunt Valley",
    tz="Etc/GMT+5",
    dc_capacity_kw=52.92,
    ac_capacity_kw=48.5,  # empirical 15-min p99.9 (48,451 W)
    n_units=7,  # 7 x ~7 kW string inverters
    lat=39.4856,
    lon=-76.6636,
    tilt=20.0,
    azimuth=180.0,
    electrical=("2716", "2721", "2726", "2731", "2736", "2741", "2746"),
    source=PvdaqLakeAdapter(
        data_dir=Path("data/1199/lake"),
        meter=LakeColumn(2714, scale=0.001),  # ac_power, W
        inverter_scale=0.001,  # invN_ac_power channels are W too
    ),
    weather=OpenMeteoWeather(
        start="2010-05-26",
        end="2020-07-27",
        cache_dir=Path("data/1199"),
    ),
)
