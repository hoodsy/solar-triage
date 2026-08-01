"""PVDAQ system 1239, Univ. of Maine at Presque Isle. 20.2 kW DC at
tilt 10 / azimuth 155 (southeast — the power peak stamps before noon),
single inverter, measured POA + on-site temp. Northern snow climate —
the December hourly-mean profile is ~1/7 of June's. Stamps are fixed
EST year-round. Same clean 2018-08-04 logger migration as the Agassi
family: meter kW -> W, temp °F -> °C a day later; POA stays W/m²."""

from pathlib import Path

from triage.ingest import LakeColumn, PvdaqLakeAdapter
from triage.config import SiteConfig
from triage.ingest.weather import OpenMeteoWeather

SITE = SiteConfig(
    name="PVDAQ 1239 Presque Isle",
    tz="Etc/GMT+5",
    dc_capacity_kw=20.16,
    ac_capacity_kw=20.2,  # empirical converted 15-min p99.9
    lat=46.6704,
    lon=-68.0178,
    tilt=10.0,
    azimuth=155.0,
    # healthy-day binned fit of actual/expected vs POA (0.00@37 (cut-in), 0.71@150 rel)
    low_light_k=95.0,
    source=PvdaqLakeAdapter(
        data_dir=Path("data/1239/lake"),
        meter=LakeColumn(3015, scale=1.0, breaks=(("2018-08-04", 0.0, 0.001),)),
        irradiance=LakeColumn(3018),
        temperature=LakeColumn(
            3016, offset=-32.0, scale=5 / 9, breaks=(("2018-08-05", 0.0, 1.0),)
        ),
    ),
    # measured-POA site: the met join only contributes rain_mm/snow_cm
    # (sensor temp wins the ladder) — THE snow-rule site of the fleet
    weather=OpenMeteoWeather(
        start="2011-09-18",
        end="2020-07-27",
        cache_dir=Path("data/1239"),
    ),
)
