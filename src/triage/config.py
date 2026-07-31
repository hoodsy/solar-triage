"""Site registry and per-site configuration. Declarations only, no logic.

Everything downstream reads a SiteConfig. The active site is chosen once at
startup via the TRIAGE_SITE env var (see main.py).
"""

from dataclasses import dataclass
from pathlib import Path

from triage.adapters import (
    Adapter,
    CsvAdapter,
    SolarNetworkAdapter,
    SourceFile,
    Stream,
)
from triage.weather import OpenMeteoWeather


@dataclass(frozen=True)
class SiteConfig:
    name: str
    tz: str
    dc_capacity_kw: float
    ac_capacity_kw: float
    source: Adapter
    # expected-power model facts (None when the site has measured POA)
    lat: float | None = None
    lon: float | None = None
    tilt: float | None = None
    azimuth: float | None = None
    weather: OpenMeteoWeather | None = None  # reanalysis POA; None = clear-sky
    # analysis window (None = open-ended)
    report_start: str | None = None
    report_end: str | None = None
    # tuning: generic defaults, overridable per site
    interval: str = "15min"
    derate: float = 0.8  # loss stack (heat, inverter conversion, wiring, mismatch, aging)
    coverage_min: float = 0.8  # exclude days missing >20% of intervals
    flag_threshold: float = 0.92  # flag 8%+ underperformance vs baseline
    window: int = 30  # baseline rolling window, days


SITES: dict[str, SiteConfig] = {
    # PVDAQ system 2107, "Farm Solar Array", Arbuckle CA
    "2107": SiteConfig(
        name="PVDAQ 2107",
        tz="US/Pacific",
        dc_capacity_kw=893.0,
        # measured 15-min max ≈ 706 kW (healthy-era 2024): the inverters
        # overdrive their 662.4 kW summed nameplate (24 × TRIO-27.6), so
        # ceiling-relative rules use the empirical value
        ac_capacity_kw=705.0,
        # Arbuckle CA: met trust ladder only (the thermal rule wants ambient
        # temp). tilt/azimuth stay None — geometry is unverified, so no
        # clearsky column and the weather rule stays inert on this site.
        lat=39.01,
        lon=-122.06,
        report_start="2024-01-01",
        report_end="2024-11-30",
        source=CsvAdapter(
            data_dir=Path("data/2107/data"),
            meter=Stream(  # keep="last" default: newest vintage wins on overlap
                files=(
                    "2107_meter_15m_data.csv",  # 2017-01 → 2023-11
                    "2107_meter_15m_data_2024.csv",  # 2024-01 → 2024-11
                    "2107_meter_15m_data_2025.csv",  # 2024-02 → 2025-12
                ),
                column="meter_revenue_grade_ac_output_meter_149578",
            ),
            irradiance=Stream(
                files=(
                    "2107_irradiance_data.csv",
                    "2107_irradiance_data_2024.csv",
                    SourceFile(  # the odd one out: UTC stamps, different column
                        "2107_irradiance_15m_data_2025.csv",
                        time_col="utc_measured_on",
                        tz="UTC",
                    ),
                ),
                column="poa_irradiance_o_149574",
                keep="first",  # 5-min files beat the 15-min 2025 file on overlap
                resample=True,
            ),
            temperature=Stream(
                files=(
                    "2107_environment_data.csv",
                    "2107_environment_data_2024.csv",
                ),
                column="ambient_temperature_o_149575",
                fahrenheit=True,  # 44.2 at midnight Jan 1 is not celsius
            ),
        ),
    ),
    # SolarNetwork public node 120 (Auckland, NZ) — residential PV, live data
    # since 2014. No irradiance source, so expected power uses the clear-sky
    # model; flag thresholds untuned for this site. The fixed study window
    # spans a real outage: zero output Dec 2025 - Jan 2026 while telemetry
    # stayed live, recovering in February.
    "sn120": SiteConfig(
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
    ),
}
