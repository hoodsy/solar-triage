"""PVDAQ system 1283, NREL Research Support Facility II, Golden CO.
408 kW DC at tilt 10 / azimuth 165, measured POA + °C ambient temp,
fixed-MST stamps like its RSF1 neighbor. Fetched window 2013-2022 (the
parquet mirror ends 2022-02; the CSV lake claims 2024). Meter channel
is kW until the migration (this logger flipped 2018-08-05, a day after
the fleet), W after — clean break. The plant HAS two inverters but
inv1's kW channel (1043) is flat zero for the entire span, so
sub-metering is left off — a dead channel would fake divergence daily.
The refcell POA (1054) spikes to 4999.8 in 2017; the thermopile
channel (1055) drives expected power instead."""

from pathlib import Path

from triage.adapters import LakeColumn, PvdaqLakeAdapter
from triage.config import SiteConfig

SITE = SiteConfig(
    name="PVDAQ 1283 NREL RSF2",
    tz="Etc/GMT+7",
    dc_capacity_kw=408.24,
    ac_capacity_kw=369.9,  # empirical converted 15-min p99.9
    lat=39.7409,
    lon=-105.1711,
    tilt=10.0,
    azimuth=165.0,
    source=PvdaqLakeAdapter(
        data_dir=Path("data/1283/lake"),
        meter=LakeColumn(1040, scale=1.0, breaks=(("2018-08-05", 0.0, 0.001),)),
        irradiance=LakeColumn(1055),
        temperature=LakeColumn(1053),  # already °C
    ),
)
