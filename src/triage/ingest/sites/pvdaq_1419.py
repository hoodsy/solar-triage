"""PVDAQ system 1419, Clark County NV - Hollywood Rec Center. 40 kW DC
at tilt 10 / azimuth 210, two asymmetric inverters (~16 + ~19 kW) whose
kwac channels flip kW -> W at the county's 2017-03-29 migration (clean,
zero overlap); the meter is their NaN-poisoned sum. Measured POA +
ambient °C; DST-aware local stamps."""

from pathlib import Path

from triage.ingest import LakeColumn, PvdaqLakeAdapter
from triage.config import SiteConfig

BREAK = (("2017-03-29", 0.0, 0.001),)

SITE = SiteConfig(
    name="PVDAQ 1419 Hollywood Rec",
    tz="America/Los_Angeles",
    dc_capacity_kw=40.0,
    ac_capacity_kw=34.9,  # empirical summed 15-min p99.9
    n_units=2,
    lat=36.1534,
    lon=-115.0256,
    tilt=10.0,
    azimuth=210.0,
    electrical=("4797", "4799"),
    source=PvdaqLakeAdapter(
        data_dir=Path("data/1419/lake"),
        meter=(
            LakeColumn(4797, scale=1.0, breaks=BREAK),
            LakeColumn(4799, scale=1.0, breaks=BREAK),
        ),
        irradiance=LakeColumn(4796),
        temperature=LakeColumn(4803),  # °C
        inverter_scale=1.0,
        inverter_breaks=BREAK,
    ),
)
