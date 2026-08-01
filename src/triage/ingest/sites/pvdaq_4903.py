"""PVDAQ system 4903, NIST Roof Array 1, Gaithersburg MD. 73.7 kW DC at
tilt 10 / azimuth 180, 1-min data 2014-08 -> 2018-03, humid-subtropical
(Cfa). The metadata Metrics section is empty and the CSV column names
carry no metric-id suffixes — the id map was recovered by aligning one
CSV day against the same parquet day and matching values exactly:
inverter AC power (kW) = 82728, thermopile POA = 82699, ambient °C =
82702. Single inverter, no unit-era breaks (span predates the 2018-08
migration), -999 sentinels handled by the adapter. Stamps fixed EST.
Clipping census: 3 plateau days in 761 — not a clipping site."""

from pathlib import Path

from triage.ingest import LakeColumn, PvdaqLakeAdapter
from triage.config import SiteConfig
from triage.ingest.weather import OpenMeteoWeather

SITE = SiteConfig(
    name="PVDAQ 4903 NIST Roof",
    tz="Etc/GMT+5",
    dc_capacity_kw=73.7,
    ac_capacity_kw=59.5,  # empirical 15-min p99.9
    lat=39.1354,
    lon=-77.2156,
    tilt=10.0,
    azimuth=180.0,
    source=PvdaqLakeAdapter(
        data_dir=Path("data/4903/lake"),
        meter=LakeColumn(82728),  # already kW
        irradiance=LakeColumn(82699),
        temperature=LakeColumn(82702),  # already °C
    ),
    # met join for Maryland snow (rain/snow only; sensor temp wins)
    weather=OpenMeteoWeather(
        start="2014-08-01",
        end="2018-03-15",
        cache_dir=Path("data/4903"),
    ),
)
