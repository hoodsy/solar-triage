"""PVDAQ system 14597, PVDB fleet, Santa Ana CA. 179 kW DC commercial, two ~87 kW inverters, kW-scale channels.
CSV-lake-only (the parquet mirror froze in 2022): ingested via
scripts/convert_lake_csv.py, which melts the yearly wide CSVs into the
long-parquet tree with manifest-assigned metric ids
(data/14597/lake_manifest.json). Stamps are naive UTC (June peak at raw
hour 20 = 13:00 PDT) — stamp_tz converts to site-local. Sentinel is
-1000000, masked at conversion. No irradiance or met sensors:
Open-Meteo tier; geometry is a SoCal-commercial-roof guess."""

from pathlib import Path

from triage.ingest import LakeColumn, PvdaqLakeAdapter
from triage.config import SiteConfig
from triage.ingest.weather import OpenMeteoWeather

INV = (28, 29)

SITE = SiteConfig(
    name="PVDAQ 14597 PVDB Santa Ana B",
    tz="America/Los_Angeles",
    dc_capacity_kw=179.0,
    ac_capacity_kw=174.0,  # empirical summed 15-min p99.9
    n_units=2,
    lat=33.70278,
    lon=-117.90238,
    tilt=10.0,
    azimuth=180.0,
    electrical=tuple(str(m) for m in INV),
    source=PvdaqLakeAdapter(
        data_dir=Path("data/14597/lake"),
        meter=tuple(LakeColumn(m) for m in INV),  # already kW
        stamp_tz="UTC",
    ),
    weather=OpenMeteoWeather(
        start="2016-01-27",
        end="2019-06-21",
        cache_dir=Path("data/14597"),
    ),
)
