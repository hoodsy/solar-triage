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


@dataclass(frozen=True)
class SiteConfig:
    name: str
    tz: str
    dc_capacity_kw: float
    ac_capacity_kw: float
    source: Adapter
    # clear-sky expected-power facts (None when the site has measured POA)
    lat: float | None = None
    lon: float | None = None
    tilt: float | None = None
    azimuth: float | None = None
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
        report_start="2024-01-01",
        report_end="2024-11-30",
        source=CsvAdapter(
            data_dir=Path("data/2107/data"),
            meter=Stream(
                files=(
                    SourceFile("2107_meter_15m_data.csv"),  # 2017-01 → 2023-11
                    SourceFile("2107_meter_15m_data_2024.csv"),  # 2024-01 → 2024-11
                    SourceFile("2107_meter_15m_data_2025.csv"),  # 2024-02 → 2025-12
                ),
                column="meter_revenue_grade_ac_output_meter_149578",
                keep="last",  # newest vintage wins on overlap
            ),
            irradiance=Stream(
                files=(
                    SourceFile("2107_irradiance_data.csv"),
                    SourceFile("2107_irradiance_data_2024.csv"),
                    SourceFile(
                        "2107_irradiance_15m_data_2025.csv",
                        time_col="utc_measured_on",
                        tz="UTC",
                    ),
                ),
                column="poa_irradiance_o_149574",
                keep="first",  # 5-min files beat the 15-min 2025 file on overlap
                resample=True,
            ),
        ),
    ),
    # SolarNetwork public node 108 (Auckland, NZ) — live demo node, polled over
    # HTTP. No irradiance source, so expected power uses the clear-sky model.
    # Capacities and geometry are UNVERIFIED estimates (node metadata is not
    # public; winter midday output observed ~27 kW); flag thresholds untuned.
    "sn108": SiteConfig(
        name="SolarNetwork node 108",
        tz="Pacific/Auckland",
        # unverified estimates, sized so clear-sky expected clears the observed
        # winter actual peak of ~36 kW (calibration rule: expected >= actual on
        # clear days); revisit against summer data
        dc_capacity_kw=60.0,
        ac_capacity_kw=45.0,
        lat=-36.85,
        lon=174.76,  # Auckland area
        tilt=25.0,
        azimuth=0.0,  # north-facing guess (southern hemisphere)
        source=SolarNetworkAdapter(node_id=108, power_source_id="DB"),
    ),
}
