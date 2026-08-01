"""PVDAQ system 1403, NREL Regional Test Center baseline, Cocoa Beach FL.
6 kW DC test array at tilt 35 / azimuth 180, 1-min data 2014-2020 —
the fleet's only humid-subtropical (Cfa coastal) site. Two ~2.8 kW
inverters with W-scale AC channels (summed meter, referee-graded pair),
thermopile POA + 2 refcells. Ambient temp is trustworthy 2016+ only —
the 2014-15 readings track a sun-exposed/module sensor (July median
37.7 °C, max 59); the quality gate's plausibility limits absorb the
worst of it. Stamps fixed EST; no unit-era breaks."""

from pathlib import Path

from triage.ingest import LakeColumn, PvdaqLakeAdapter
from triage.config import SiteConfig

SITE = SiteConfig(
    name="PVDAQ 1403 RTC Cocoa Beach",
    tz="Etc/GMT+5",
    dc_capacity_kw=6.0,
    ac_capacity_kw=5.7,  # empirical summed 15-min p99.9
    n_units=2,
    lat=28.405,
    lon=-80.7709,
    tilt=35.0,
    azimuth=180.0,
    electrical=("4207", "4213"),
    source=PvdaqLakeAdapter(
        data_dir=Path("data/1403/lake"),
        meter=(LakeColumn(4207, scale=0.001), LakeColumn(4213, scale=0.001)),
        irradiance=LakeColumn(4214),
        temperature=LakeColumn(4217),  # °C
        inverter_scale=0.001,
    ),
)
