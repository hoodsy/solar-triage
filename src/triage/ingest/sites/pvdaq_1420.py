"""PVDAQ system 1420, Clark County NV - Government Center. 30 kW DC at
tilt 10 / azimuth 180, single inverter whose kwac channel flips kW -> W
at the county's 2017-03-29 migration (clean). Measured POA; NO ambient
sensor — the module-temp channel exists but flips °F -> °C mid-span and
module != ambient, so the thermal rule stays inert here by choice.
DST-aware local stamps."""

from pathlib import Path

from triage.ingest import LakeColumn, PvdaqLakeAdapter
from triage.config import SiteConfig

SITE = SiteConfig(
    name="PVDAQ 1420 Government Center",
    tz="America/Los_Angeles",
    dc_capacity_kw=30.0,
    ac_capacity_kw=30.0,  # empirical 15-min p99.9 pins at nameplate
    lat=36.1654,
    lon=-115.1534,
    tilt=10.0,
    azimuth=180.0,
    source=PvdaqLakeAdapter(
        data_dir=Path("data/1420/lake"),
        meter=LakeColumn(4812, scale=1.0, breaks=(("2017-03-29", 0.0, 0.001),)),
        irradiance=LakeColumn(4810),
    ),
)
