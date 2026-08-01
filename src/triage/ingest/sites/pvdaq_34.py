"""PVDAQ system 34, Andre Agassi Preparatory Academy Building A, Las
Vegas NV. 146.6 kW DC roof, single inverter, measured POA + on-site
temp — desert-soiling territory. Stamps are fixed PST year-round (peak
stamps hour 11 in June AND December). The 2018-08-04 logger migration
flips units (clean break, zero overlap days): ac power hectowatt -> W,
temp °F -> °C a day later. POA stays W/m² throughout."""

from pathlib import Path

from triage.ingest import LakeColumn, PvdaqLakeAdapter
from triage.config import SiteConfig

SITE = SiteConfig(
    name="PVDAQ 34 Agassi A",
    tz="Etc/GMT+8",
    dc_capacity_kw=146.64,
    ac_capacity_kw=123.9,  # empirical converted 15-min p99.9
    lat=36.1952,
    lon=-115.1582,
    tilt=11.2,
    azimuth=180.0,
    source=PvdaqLakeAdapter(
        data_dir=Path("data/34/lake"),
        meter=LakeColumn(2695, scale=0.1, breaks=(("2018-08-04", 0.0, 0.001),)),
        irradiance=LakeColumn(2679),
        temperature=LakeColumn(
            2688, offset=-32.0, scale=5 / 9, breaks=(("2018-08-05", 0.0, 1.0),)
        ),
    ),
)
