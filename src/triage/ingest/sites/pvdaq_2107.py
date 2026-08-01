"""PVDAQ system 2107, "Farm Solar Array", Arbuckle CA."""

from pathlib import Path

from triage.ingest import PvdaqAdapter, SourceFile, Stream
from triage.config import SiteConfig

SITE = SiteConfig(
    name="PVDAQ 2107",
    tz="US/Pacific",
    dc_capacity_kw=893.0,
    # measured 15-min max ≈ 706 kW (healthy-era 2024): the inverters
    # overdrive their 662.4 kW summed nameplate (24 × TRIO-27.6), so
    # ceiling-relative rules use the empirical value
    ac_capacity_kw=705.0,
    n_units=24,  # 24 x TRIO-27.6: deficits quantize to ~4.2% steps
    # measured POA + 24-unit granularity: a single dead inverter dips PI to
    # only ~0.96, so the absolute guard needs headroom; the referee grades
    # every marginal flag against the fleet anyway
    pi_ceiling=0.98,
    # geometry: PVDAQ metadata says tilt 25 / azimuth 180, but the
    # clear-day POA fit lands at azimuth 193 with 3.2% residual (vs 6.0%
    # at 180) — the design tilt built to MAGNETIC south (declination
    # +13 E). Fitted as-built values win over paperwork.
    lat=38.996306,
    lon=-122.134111,
    tilt=25.0,
    azimuth=193.0,
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
)
