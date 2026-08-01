"""PVDAQ system 4902, NIST Ground Array 1, Gaithersburg MD.
270.7 kW DC at tilt 20 / azimuth 180, 1-min 2014-2018, sibling of the
roof array (4903). Channel map recovered the same way (CSV-parquet
value alignment; the inverter-power alignment itself hit a sentinel day,
so the plant kW channel was found by magnitude + bell shape instead:
82633, stable 246-256 kW p99.9 all years). POA 82595, ambient °C 82596.
Fixed EST; met join for Maryland snow."""

from pathlib import Path

from triage.ingest import LakeColumn, PvdaqLakeAdapter
from triage.config import SiteConfig
from triage.ingest.weather import OpenMeteoWeather

SITE = SiteConfig(
    name="PVDAQ 4902 NIST Ground",
    tz="Etc/GMT+5",
    dc_capacity_kw=270.7,
    ac_capacity_kw=248.0,  # empirical 15-min p99.9
    lat=39.1319,
    lon=-77.2141,
    tilt=20.0,
    azimuth=180.0,
    source=PvdaqLakeAdapter(
        data_dir=Path("data/4902/lake"),
        meter=LakeColumn(82633),  # already kW
        irradiance=LakeColumn(82595),
        temperature=LakeColumn(82596),
    ),
    weather=OpenMeteoWeather(
        start="2014-07-29",
        end="2018-03-15",
        cache_dir=Path("data/4902"),
    ),
)
