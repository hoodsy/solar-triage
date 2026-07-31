"""PVDAQ system 9069, "Simon Solar Farm", Social Circle GA — 2023 Solar
Data Prize utility site: 38.7 MW DC, 40 x 825 kW inverters, fixed ground
mount. Two revenue-meter eras (meter_1 2016-02 → 2019-04, meter_2
2020-03 → 2023-11) separated by a year-long metering gap; the study
window is the meter_2 era."""

from pathlib import Path

from triage.adapters import PvdaqAdapter, Stream
from triage.config import SiteConfig

SITE = SiteConfig(
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
)
