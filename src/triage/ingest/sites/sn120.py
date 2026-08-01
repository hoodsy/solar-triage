"""SolarNetwork public node 120 (Auckland, NZ) — residential PV, live data
since 2014. No irradiance source, so expected power uses the clear-sky
model; flag thresholds untuned for this site. The fixed study window
spans a real outage: zero output Dec 2025 - Jan 2026 while telemetry
stayed live, recovering in February."""

from pathlib import Path

from triage.ingest import SolarNetworkAdapter
from triage.config import SiteConfig
from triage.ingest.weather import OpenMeteoWeather

SITE = SiteConfig(
    name="SolarNetwork node 120",
    tz="Pacific/Auckland",
    # sized from observed output (summer 15-min peak 1.53 kW, instantaneous
    # 1.88 kW); geometry is an unverified Auckland guess
    dc_capacity_kw=2.0,
    ac_capacity_kw=1.9,
    lat=-36.85,
    lon=174.76,
    tilt=25.0,
    azimuth=0.0,  # north-facing (southern hemisphere)
    source=SolarNetworkAdapter(
        node_id=120,
        power_source_id="Solar",
        start="2025-08-01",  # healthy baseline before the November decline
        end="2026-03-01",  # through post-repair recovery
        cache_dir=Path("data/sn120"),
    ),
    weather=OpenMeteoWeather(
        start="2025-08-01",
        end="2026-03-01",
        cache_dir=Path("data/sn120"),
    ),
)
