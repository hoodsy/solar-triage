"""PVDAQ system 1276, Andre Agassi Preparatory Academy Building B, Las
Vegas NV. 68.5 kW DC at a shallow 5° tilt (empirical AC ceiling 0.72 of
DC — the low tilt costs real yield), single inverter, measured POA +
on-site temp. Same campus, same fixed-PST stamps, and same clean
2018-08-04 unit migration as system 34."""

from pathlib import Path

from triage.ingest import LakeColumn, PvdaqLakeAdapter
from triage.config import SiteConfig

SITE = SiteConfig(
    name="PVDAQ 1276 Agassi B",
    tz="Etc/GMT+8",
    dc_capacity_kw=68.48,
    ac_capacity_kw=49.5,  # empirical converted 15-min p99.9
    lat=36.1952,
    lon=-115.1582,
    tilt=5.0,
    azimuth=180.0,
    source=PvdaqLakeAdapter(
        data_dir=Path("data/1276/lake"),
        meter=LakeColumn(3040, scale=0.1, breaks=(("2018-08-04", 0.0, 0.001),)),
        irradiance=LakeColumn(3026),
        temperature=LakeColumn(
            3028, offset=-32.0, scale=5 / 9, breaks=(("2018-08-05", 0.0, 1.0),)
        ),
    ),
)
