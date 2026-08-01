"""PVDAQ system 1367, City of Henderson NV Aquatic Complex. 277 kW DC,
tilt 12 / azimuth 172, three ~60-97 kW inverters each with a full-span
W-scale AC channel (3083/3086/3089) — the plant-total channel dies in
2018, so ac_power_kw is the NaN-poisoned inverter sum and the same three
channels feed the referee. Ambient temp (4193, added 2015) is KELVIN
until the 2018-08-04 12:01 logger migration, °C after — zero overlap.
Stamps fixed PST like the Agassi campus. No irradiance — Open-Meteo
tier. Inverter 3 (3089) spends 2019 essentially dead: real events."""

from pathlib import Path

from triage.ingest import LakeColumn, PvdaqLakeAdapter
from triage.config import SiteConfig
from triage.ingest.weather import OpenMeteoWeather

SITE = SiteConfig(
    name="PVDAQ 1367 Henderson",
    tz="Etc/GMT+8",
    dc_capacity_kw=277.16,
    ac_capacity_kw=233.8,  # empirical 15-min p99.9 of the summed inverters
    n_units=3,
    lat=36.033,
    lon=-114.9516,
    tilt=12.0,
    azimuth=172.0,
    electrical=("3083", "3086", "3089"),
    source=PvdaqLakeAdapter(
        data_dir=Path("data/1367/lake"),
        meter=(
            LakeColumn(3083, scale=0.001),
            LakeColumn(3086, scale=0.001),
            LakeColumn(3089, scale=0.001),
        ),
        temperature=LakeColumn(  # Kelvin era then °C after the migration
            4193, offset=-273.15, scale=1.0,
            breaks=(("2018-08-04", 0.0, 1.0),),
        ),
        inverter_scale=0.001,
    ),
    weather=OpenMeteoWeather(
        start="2013-05-08",
        end="2020-05-25",
        cache_dir=Path("data/1367"),
    ),
)
