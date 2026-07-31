"""Site registry and per-site configuration. Declarations only, no logic.

Everything downstream reads a SiteConfig. The active site is chosen once at
startup via the TRIAGE_SITE env var (see main.py).
"""

from dataclasses import dataclass
from pathlib import Path

from triage.adapters import (
    Adapter,
    PvdaqAdapter,
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
    # per-inverter electrical streams (empty = no sub-metering, no referee)
    electrical: tuple[str, ...] = ()
    # tuning: generic defaults, overridable per site
    n_units: int = 1  # inverters/strings: real partial loss quantizes to capacity/n_units
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
        n_units=24,  # 24 x TRIO-27.6: deficits quantize to ~4.2% steps
        # geometry: PVDAQ metadata says tilt 25 / azimuth 180, but the
        # clear-day POA fit lands at azimuth 193 with 3.2% residual (vs 6.0%
        # at 180) — the design tilt built to MAGNETIC south (declination
        # +13 E). Fitted as-built values win over paperwork.
        lat=38.996306,
        lon=-122.134111,
        tilt=25.0,
        azimuth=193.0,
        report_start="2024-01-01",
        report_end="2024-11-30",
        electrical=(  # vintage order mirrors the meter stream
            "2107_electrical_data.csv",
            "2107_electrical_data_2024.csv",
            "2107_electrical_data_2025.csv",
        ),
        source=PvdaqAdapter(
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
    # PVDAQ system 9069, "Simon Solar Farm", Social Circle GA — 2023 Solar
    # Data Prize utility site: 38.7 MW DC, 40 x 825 kW inverters, fixed
    # ground mount. Two revenue-meter eras (meter_1 2016-02 → 2019-04,
    # meter_2 2020-03 → 2023-11) separated by a year-long metering gap;
    # the study window is the meter_2 era.
    "9069": SiteConfig(
        name="PVDAQ 9069",
        # naive local stamps, DST-aware: June output peaks at stamp 13:00,
        # December at 12:00 — the 1h summer drift rules out fixed UTC-5
        tz="US/Eastern",
        dc_capacity_kw=38687.0,
        # empirical: meter_2-era 15-min max 32,092 kW, just under the 33 MW
        # summed inverter nameplate (40 x 825)
        ac_capacity_kw=32100.0,
        n_units=40,
        # real geometry from PVDAQ metadata — weather rule live on this site
        lat=33.6762,
        lon=-83.676,
        tilt=20.0,
        azimuth=180.0,  # south-facing
        report_start="2020-04-01",
        report_end="2023-11-28",
        electrical=("9069_electrical_ac.csv",),
        source=PvdaqAdapter(
            data_dir=Path("data/9069/data"),
            meter=Stream(
                files=("9069_meter_data.csv",),
                column="meter_2_ac_power_(kw)_meter_151053",
                resample=True,  # 5-min source -> 15-min grid
            ),
            irradiance=Stream(
                files=("9069_irradiance_data.csv",),
                # chosen by stale-screening, not raw coverage: cell_01 is 3%
                # stale / 0 negatives / 0.96 coverage, while higher-coverage
                # cells freeze at garbage for up to 39% of their readings
                # (cell_04 sticks at 1271 W/m2 for days at a time)
                column="reference_cell_01_poa_irradiance_(w/m2)_o_150232",
                resample=True,
            ),
            temperature=Stream(
                files=("9069_environment_data.csv",),
                column="weather_station_01_ambient_temperature_(sensor_1)_(c)_o_150245",
                resample=True,  # already celsius, unlike 2107
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
