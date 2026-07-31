"""PVDAQ system 1433, NREL RSF1 parking structure, Golden CO. 449 kW DC
at tilt 10 / azimuth 180, single metered channel already in kW, POA in
W/m², ambient temp in °C — the one lake site with civilized units. 15-min
native cadence. Stamps are fixed MST (POA centers on the 11/12 stamp
boundary ≈ solar noon under end-of-interval labels). The parquet mirror
for this system ends 2018-05 even though the census counts CSV years to
2024 — the 2010-2018 span is what we take."""

from pathlib import Path

from triage.adapters import LakeColumn, PvdaqLakeAdapter
from triage.config import SiteConfig
from triage.weather import OpenMeteoWeather

SITE = SiteConfig(
    name="PVDAQ 1433 NREL RSF1",
    tz="Etc/GMT+7",
    dc_capacity_kw=449.28,
    ac_capacity_kw=360.0,  # empirical 15-min p99.9, kW channel
    lat=39.7404,
    lon=-105.1719,
    tilt=10.0,
    azimuth=180.0,
    # healthy-day binned fit of actual/expected vs POA (0.38@37, 0.77@150 rel)
    low_light_k=55.0,
    source=PvdaqLakeAdapter(
        data_dir=Path("data/1433/lake"),
        meter=LakeColumn(5069),  # already kW
        irradiance=LakeColumn(5061),
        temperature=LakeColumn(5062),  # already °C
    ),
    # measured-POA site: the met join only contributes rain_mm/snow_cm
    # (sensor temp wins the ladder) — Golden winters need the snow rule
    weather=OpenMeteoWeather(
        start="2010-12-31",
        end="2018-06-01",
        cache_dir=Path("data/1433"),
    ),
)
