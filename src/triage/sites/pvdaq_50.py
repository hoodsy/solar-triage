"""PVDAQ system 50, NREL x-Si 6 test array, Golden CO.
6 kW DC at tilt 45 / azimuth 158, 15-min data 1994-2023 — twenty-nine
years, the fleet's longest record. W-scale ac_power, POA, ambient °C.
Old DAS files stamp some rows in 1822 — the adapter clamp cuts to the
real span. Fixed MST; Golden winters get the snow rule via the met
join. Low-light curve unfitted (k=0) — revisit if its dark days flag."""

from pathlib import Path

from triage.adapters import LakeColumn, PvdaqLakeAdapter
from triage.config import SiteConfig
from triage.weather import OpenMeteoWeather

SITE = SiteConfig(
    name="PVDAQ 50 NREL x-Si 6",
    tz="Etc/GMT+7",
    dc_capacity_kw=6.0,
    ac_capacity_kw=6.5,  # empirical 15-min p99.9
    lat=39.742,
    lon=-105.1727,
    tilt=45.0,
    azimuth=158.0,
    source=PvdaqLakeAdapter(
        data_dir=Path("data/50/lake"),
        meter=LakeColumn(752, scale=0.001),
        irradiance=LakeColumn(750),
        temperature=LakeColumn(759),
        start="1994-01-01",
    ),
    weather=OpenMeteoWeather(
        start="1994-01-01",
        end="2023-03-01",
        cache_dir=Path("data/50"),
    ),
)
