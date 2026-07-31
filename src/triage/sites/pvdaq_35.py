"""PVDAQ system 35, Andre Agassi Preparatory Academy Gymnasium, Las
Vegas NV. 121.7 kW DC roof, single inverter, measured POA + °F-era
temps. The census says azimuth 270 but the power curve tracks the POA
sensor with both peaking at solar noon — the array is SOUTH-facing;
config carries the empirical value. Same clean 2018-08-04 campus
migration: meter hectowatt -> W, temp °F -> °C a day later. Clipping
census on converted data: 1 day in 1,974 — not a clipping site."""

from pathlib import Path

from triage.adapters import LakeColumn, PvdaqLakeAdapter
from triage.config import SiteConfig

SITE = SiteConfig(
    name="PVDAQ 35 Agassi Gym",
    tz="Etc/GMT+8",
    dc_capacity_kw=121.68,
    ac_capacity_kw=100.0,  # empirical converted p99.9 both eras (~100 kW)
    lat=36.1952,
    lon=-115.1582,
    tilt=10.0,  # census blank; campus roofs run 5-11
    azimuth=180.0,  # empirical (census 270 is wrong)
    source=PvdaqLakeAdapter(
        data_dir=Path("data/35/lake"),
        meter=LakeColumn(2713, scale=0.1, breaks=(("2018-08-04", 0.0, 0.001),)),
        irradiance=LakeColumn(2699),
        temperature=LakeColumn(
            2706, offset=-32.0, scale=5 / 9, breaks=(("2018-08-05", 0.0, 1.0),)
        ),
    ),
)
