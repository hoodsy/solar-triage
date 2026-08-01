"""PVDAQ system 1418, Clark County NV - Desert Breeze. 42 kW DC at
tilt 10 / azimuth 138 (southeast — winter peak stamps 10-11), three
~13 kW inverters, measured POA + ambient °C (despite the "_f" column
name — names lie, magnitudes don't). The county-wide logger migration
flips every kwac channel kW -> W on 2017-03-29, clean, zero overlap;
the plant total (5048) stayed W all span and serves as the meter.
Stamps are DST-aware local, unlike the fixed-PST Agassi fleet."""

from pathlib import Path

from triage.ingest import LakeColumn, PvdaqLakeAdapter
from triage.config import SiteConfig

BREAK = (("2017-03-29", 0.0, 0.001),)

SITE = SiteConfig(
    name="PVDAQ 1418 Desert Breeze",
    tz="America/Los_Angeles",
    dc_capacity_kw=42.0,
    ac_capacity_kw=37.9,  # empirical 15-min p99.9
    n_units=3,
    lat=36.1253,
    lon=-115.2713,
    tilt=10.0,
    azimuth=138.0,
    electrical=("4786", "4788", "4790"),
    source=PvdaqLakeAdapter(
        data_dir=Path("data/1418/lake"),
        meter=LakeColumn(5048, scale=0.001),  # W all span, no break
        irradiance=LakeColumn(4785),
        temperature=LakeColumn(4792),  # °C
        inverter_scale=1.0,  # kW era first
        inverter_breaks=BREAK,
    ),
)
