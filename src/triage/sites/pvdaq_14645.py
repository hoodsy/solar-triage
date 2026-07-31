"""PVDAQ system 14645, PVDB fleet, Costa Mesa CA. 485.1 kW DC commercial across SEVENTEEN ~28 kW string inverters — the deepest referee fleet after 9069. The summed ceiling pins at exactly 408 kW three years running: ceiling-limited behavior worth watching.
CSV-lake-only (the parquet mirror froze in 2022): ingested via
scripts/convert_lake_csv.py, which melts the yearly wide CSVs into the
long-parquet tree with manifest-assigned metric ids
(data/14645/lake_manifest.json). Stamps are naive UTC (June peak at raw
hour 20 = 13:00 PDT) — stamp_tz converts to site-local. Sentinel is
-1000000, masked at conversion. No irradiance or met sensors:
Open-Meteo tier; geometry is a SoCal-commercial-roof guess."""

from pathlib import Path

from triage.adapters import LakeColumn, PvdaqLakeAdapter
from triage.config import SiteConfig
from triage.weather import OpenMeteoWeather

INV = tuple(range(122, 139))

SITE = SiteConfig(
    name="PVDAQ 14645 PVDB Costa Mesa",
    tz="America/Los_Angeles",
    dc_capacity_kw=485.1,
    ac_capacity_kw=408.0,  # empirical summed 15-min p99.9
    n_units=17,
    lat=33.70297,
    lon=-117.88759,
    tilt=10.0,
    azimuth=180.0,
    electrical=tuple(str(m) for m in INV),
    source=PvdaqLakeAdapter(
        data_dir=Path("data/14645/lake"),
        meter=tuple(LakeColumn(m) for m in INV),  # already kW
        stamp_tz="UTC",
    ),
    weather=OpenMeteoWeather(
        start="2016-11-18",
        end="2019-06-21",
        cache_dir=Path("data/14645"),
    ),
)
