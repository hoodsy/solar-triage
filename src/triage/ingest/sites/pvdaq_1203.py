"""PVDAQ system 1203, "Distributed Sun - EJ DeSeta", Wilmington DE.
197.5 kW DC roof, azimuth 205, two ~98 kW inverters each behind its own
revenue meter — ac_power_kw is the NaN-poisoned sum of the two meters
(the single total channel dies 2018-08; the meters run to 2020-07).
Stamps are DST-aware local (June peak stamps 13, December 12 — the
9069 signature), unlike the fixed-EST 1199/1202 siblings. On-site GHI
exists but the pipeline wants POA, so expected power is Open-Meteo;
ambient temp is the on-site sensor. The 2018-08-04 logger migration
flips every channel's units mid-history (verified clean, no overlap):
meters kW -> W, "hw" inverter channels hectowatt -> W, temp °F -> °C
a day later. The 124 sub-kilowatt-band days after the break are real
outages (plant down, -80 W night draw), not unit confusion."""

from pathlib import Path

from triage.ingest import LakeColumn, PvdaqLakeAdapter
from triage.config import SiteConfig
from triage.ingest.weather import OpenMeteoWeather

SITE = SiteConfig(
    name="PVDAQ 1203 EJ DeSeta",
    tz="America/New_York",
    dc_capacity_kw=197.47,
    ac_capacity_kw=190.0,  # empirical p99.9 of the summed meters, both eras ~189-190
    n_units=2,  # two ~98 kW central inverters
    lat=39.7325,
    lon=-75.5511,
    tilt=20.0,
    azimuth=205.0,
    electrical=("2895", "2902"),  # invN_ac_power_hw
    source=PvdaqLakeAdapter(
        data_dir=Path("data/1203/lake"),
        meter=(
            LakeColumn(2909, scale=1.0, breaks=(("2018-08-04", 0.0, 0.001),)),
            LakeColumn(2910, scale=1.0, breaks=(("2018-08-04", 0.0, 0.001),)),
        ),
        temperature=LakeColumn(  # °F era then °C after the swap
            2891, offset=-32.0, scale=5 / 9, breaks=(("2018-08-05", 0.0, 1.0),)
        ),
        inverter_scale=0.1,  # hectowatts until the swap
        inverter_breaks=(("2018-08-04", 0.0, 0.001),),
    ),
    weather=OpenMeteoWeather(
        start="2011-01-19",
        end="2020-07-27",
        cache_dir=Path("data/1203"),
    ),
)
