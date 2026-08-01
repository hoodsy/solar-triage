"""PVDAQ system 1277, Andre Agassi Preparatory Academy Building C, Las
Vegas NV. 40.6 kW DC roof, single inverter, measured POA + on-site
temp. Same campus, same fixed-PST stamps, and same clean 2018-08-04
unit migration as systems 34 and 1276."""

from pathlib import Path

from triage.ingest import LakeColumn, PvdaqLakeAdapter
from triage.config import SiteConfig

SITE = SiteConfig(
    name="PVDAQ 1277 Agassi C",
    tz="Etc/GMT+8",
    dc_capacity_kw=40.56,
    ac_capacity_kw=36.9,  # empirical converted 15-min p99.9
    lat=36.1952,
    lon=-115.1582,
    tilt=10.0,
    azimuth=180.0,
    source=PvdaqLakeAdapter(
        data_dir=Path("data/1277/lake"),
        meter=LakeColumn(3055, scale=0.1, breaks=(("2018-08-04", 0.0, 0.001),)),
        irradiance=LakeColumn(3041),
        temperature=LakeColumn(
            3043, offset=-32.0, scale=5 / 9, breaks=(("2018-08-05", 0.0, 1.0),)
        ),
    ),
)
