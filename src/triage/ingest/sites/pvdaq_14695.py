"""PVDAQ system 14695, PVDB fleet, Santa Ana CA. 293.1 kW DC commercial on
TWO asymmetric inverters (~85 + ~210 kW, like 1278's 100+40 split) —
referee x2. HELD-OUT MODEL TEST SITE (2026-08-01): onboarded to evaluate
the trained student on a plant absent from its training set; same
CSV-lake cohort and naive-UTC stamps as the 14645/14601/14597 trio (June
peak at raw hour 20 = 13:00 PDT). Native 5-min cadence.
The seven meter_33xx channels are a trap: 3338/3339 mirror the two
inverters, 3343 is the plant total, the rest appear and vanish by year,
and the meter-sum double-counts the plant (~2x the inverter sum) —
ingest the inverter pair only, summed as the meter. Channels are true kW
(summed p99.9 295 vs 293 kW DC, no unit flips); ac_capacity is the
empirical summed 15-min p99.9. Geometry is a SoCal-commercial-roof
guess."""

from pathlib import Path

from triage.ingest import LakeColumn, PvdaqLakeAdapter
from triage.config import SiteConfig
from triage.ingest.weather import OpenMeteoWeather

INV = (29, 30)  # ac_power_inv_31112, ac_power_inv_31113

SITE = SiteConfig(
    name="PVDAQ 14695 PVDB Santa Ana",
    tz="America/Los_Angeles",
    dc_capacity_kw=293.1,
    ac_capacity_kw=295.0,  # empirical summed 15-min p99.9
    n_units=2,
    lat=33.74400,
    lon=-117.87472,
    tilt=10.0,
    azimuth=180.0,
    electrical=tuple(str(m) for m in INV),
    source=PvdaqLakeAdapter(
        data_dir=Path("data/14695/lake"),
        meter=tuple(LakeColumn(m) for m in INV),  # already kW
        stamp_tz="UTC",
    ),
    weather=OpenMeteoWeather(
        start="2016-10-31",
        end="2019-06-20",
        cache_dir=Path("data/14695"),
    ),
)
