"""PVDAQ system 14601, PVDB fleet, Santa Ana CA. 622.6 kW DC commercial, two large inverters (~230 + ~420 kW) with kW-scale AC channels — the referee grades the pair.
CSV-lake-only (the parquet mirror froze in 2022): ingested via
scripts/convert_lake_csv.py, which melts the yearly wide CSVs into the
long-parquet tree with manifest-assigned metric ids
(data/14601/lake_manifest.json). Stamps are naive UTC (June peak at raw
hour 20 = 13:00 PDT) — stamp_tz converts to site-local. Sentinel is
-1000000, masked at conversion. No irradiance or met sensors:
Open-Meteo tier; geometry is a SoCal-commercial-roof guess."""

from pathlib import Path

from triage.ingest import LakeColumn, PvdaqLakeAdapter
from triage.config import SiteConfig
from triage.ingest.weather import OpenMeteoWeather

INV = (21, 22)

SITE = SiteConfig(
    name="PVDAQ 14601 PVDB Santa Ana A",
    tz="America/Los_Angeles",
    dc_capacity_kw=622.6,
    ac_capacity_kw=640.0,  # empirical summed 15-min p99.9
    n_units=2,
    lat=33.702784,
    lon=-117.901246,
    tilt=10.0,
    azimuth=180.0,
    electrical=tuple(str(m) for m in INV),
    source=PvdaqLakeAdapter(
        data_dir=Path("data/14601/lake"),
        meter=tuple(LakeColumn(m) for m in INV),  # already kW
        stamp_tz="UTC",
    ),
    weather=OpenMeteoWeather(
        start="2015-11-14",
        end="2019-06-21",
        cache_dir=Path("data/14601"),
    ),
)
