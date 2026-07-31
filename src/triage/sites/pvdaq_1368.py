"""PVDAQ system 1368, City of Henderson NV Heritage Park. ~33 kW DC
(census blank; sized from the 28.5 kW summed-inverter ceiling), six
~4.8 kW inverters with clean W-scale channels 2013-2020 and no unit-era
breaks. The plant meter channel dies in 2018, so ac_power_kw is the
NaN-poisoned six-inverter sum and the same channels feed the referee —
inv5 (3119) visibly degrades 4.3 -> 3.6 kW across the years, real
events for the fleet grader. No POA or temp sensors: Open-Meteo tier.
Geometry is a guess (tilt 10, azimuth 195 from the fixed-PST peak-hour
signature); flag thresholds inherit the model-tier caveats."""

from pathlib import Path

from triage.adapters import LakeColumn, PvdaqLakeAdapter
from triage.config import SiteConfig
from triage.weather import OpenMeteoWeather

INV = (3099, 3104, 3109, 3114, 3119, 3124)

SITE = SiteConfig(
    name="PVDAQ 1368 Heritage Park",
    tz="Etc/GMT+8",
    dc_capacity_kw=33.0,
    ac_capacity_kw=28.5,  # empirical summed 15-min p99.9
    n_units=6,
    lat=36.033,
    lon=-114.9516,
    tilt=10.0,
    azimuth=195.0,
    electrical=tuple(str(m) for m in INV),
    source=PvdaqLakeAdapter(
        data_dir=Path("data/1368/lake"),
        meter=tuple(LakeColumn(m, scale=0.001) for m in INV),
        inverter_scale=0.001,
    ),
    weather=OpenMeteoWeather(
        start="2013-06-01",
        end="2020-07-27",
        cache_dir=Path("data/1368"),
    ),
)
