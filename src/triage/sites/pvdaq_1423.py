"""PVDAQ system 1423, NREL Regional Test Center baseline, Henderson NV.
6 kW DC test array at tilt 35 / azimuth 180, 1-min data 2015-2023,
Mojave desert (Bwh) — thermal and soiling instrument. Two ~3 kW
inverters, each with its own W-scale AC channel (meter = NaN-poisoned
sum, referee grades the pair); thermopile POA + 2 refcells; ambient in
°C. No unit-era breaks (post-2018-migration logger family). Stamps
fixed PST like the rest of the NV fleet. DC/AC ≈ 1.0 — clipping census
found 6 plateau days in 2,009, this is not a clipping site."""

from pathlib import Path

from triage.adapters import LakeColumn, PvdaqLakeAdapter
from triage.config import SiteConfig

SITE = SiteConfig(
    name="PVDAQ 1423 RTC Henderson",
    tz="Etc/GMT+8",
    dc_capacity_kw=6.0,
    ac_capacity_kw=5.9,  # empirical summed 15-min p99.9
    n_units=2,
    lat=36.0275,
    lon=-114.9215,
    tilt=35.0,
    azimuth=180.0,
    electrical=("4854", "4860"),
    source=PvdaqLakeAdapter(
        data_dir=Path("data/1423/lake"),
        meter=(LakeColumn(4854, scale=0.001), LakeColumn(4860, scale=0.001)),
        irradiance=LakeColumn(4861),
        temperature=LakeColumn(4864),  # already °C
        inverter_scale=0.001,
    ),
)
