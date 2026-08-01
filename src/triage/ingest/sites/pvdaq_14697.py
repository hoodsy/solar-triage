"""PVDAQ system 14697, PVDB fleet, Santa Ana CA. 455.3 kW DC commercial on
a SINGLE central inverter (inv_31116) plus a revenue meter (meter_3352) —
no sub-metering, so no referee: this is the meter-only Open-Meteo tier.
HELD-OUT MODEL TEST SITE (2026-08-01): onboarded to evaluate the trained
student on a plant absent from its training set; same CSV-lake cohort and
naive-UTC stamps as the 14645/14601/14597 trio (June peak at raw hour
20 = 13:00 PDT). Native 5-min cadence, mean-resampled to the 15-min grid
by the adapter. Channels are true kW (per-year p99.9 350-467 vs 455 kW
DC, no unit flips); ac_capacity is the empirical 15-min p99.9 (448).
temperature_inverter is internal inverter temp, not ambient — not
ingested. Geometry is a SoCal-commercial-roof guess."""

from pathlib import Path

from triage.ingest import LakeColumn, PvdaqLakeAdapter
from triage.config import SiteConfig
from triage.ingest.weather import OpenMeteoWeather

SITE = SiteConfig(
    name="PVDAQ 14697 PVDB Santa Ana",
    tz="America/Los_Angeles",
    dc_capacity_kw=455.3,
    ac_capacity_kw=448.0,  # empirical 15-min p99.9
    lat=33.72692,
    lon=-117.89714,
    tilt=10.0,
    azimuth=180.0,
    source=PvdaqLakeAdapter(
        data_dir=Path("data/14697/lake"),
        meter=(LakeColumn(7),),  # ac_power_inv_31116, already kW
        stamp_tz="UTC",
    ),
    weather=OpenMeteoWeather(
        start="2016-10-31",
        end="2019-06-20",
        cache_dir=Path("data/14697"),
    ),
)
