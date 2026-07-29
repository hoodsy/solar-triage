import pandas as pd

from triage.config import SITE

# Metadata units reference
# meta = json.loads(Path("data/2107/metadata/2107_system_metadata.json").read_text())
# units = {col: (m["common_name"], m["units"]) for col, m in meta["Metrics"].items()}


def build_meter() -> pd.DataFrame:
    FILES = [
        "2107_meter_15m_data.csv",  # 2017-01 → 2023-11
        "2107_meter_15m_data_2024.csv",  # 2024-01 → 2024-11
        "2107_meter_15m_data_2025.csv",  # 2024-02 → 2025-12
    ]
    meter = pd.concat(
        pd.read_csv(
            SITE.data_dir / f, parse_dates=["measured_on"], index_col="measured_on"
        )
        for f in FILES
    )
    meter = meter[~meter.index.duplicated(keep="last")].sort_index()
    meter.index = meter.index.tz_localize(
        SITE.tz,
        ambiguous="NaT",  # can't resolve the once-recorded fall-back hour
        nonexistent="shift_forward",  # shouldn't occur in this data; don't crash if it does
    )
    meter = meter[meter.index.notna()]  # drop the NaT'd ambiguous rows
    return meter


def build_irradiance() -> pd.DataFrame:
    frames = []
    FILES = [
        "2107_irradiance_data.csv",
        "2107_irradiance_data_2024.csv",
    ]
    for f in FILES:
        df = pd.read_csv(
            SITE.data_dir / f, parse_dates=["measured_on"], index_col="measured_on"
        )
        df.index = df.index.tz_localize(
            SITE.tz, ambiguous="NaT", nonexistent="shift_forward"
        )
        df = df[df.index.notna()]
        frames.append(df)

    UTC_FILE = "2107_irradiance_15m_data_2025.csv"
    utc = pd.read_csv(
        SITE.data_dir / UTC_FILE,
        parse_dates=["utc_measured_on"],
        index_col="utc_measured_on",
    )
    utc.index = utc.index.tz_localize("UTC").tz_convert(SITE.tz)
    utc.index.name = "measured_on"
    frames.append(utc)

    irradiance = pd.concat(frames)
    irradiance = irradiance[~irradiance.index.duplicated(keep="first")].sort_index()
    return irradiance


def build_dataset() -> pd.DataFrame:
    meter = build_meter().rename(columns=lambda c: "ac_power_kw")
    poa = build_irradiance().rename(columns=lambda c: "poa_wm2")
    poa_15 = poa.resample("15min", closed="right", label="right").mean()
    df = meter.join(poa_15, how="outer")
    df["expected_kw"] = SITE.dc_capacity_kw * (df["poa_wm2"] / 1000.0) * SITE.derate
    return df


def build_daily(df: pd.DataFrame) -> pd.DataFrame:
    daily = pd.DataFrame(
        {
            "actual_kwh": df["ac_power_kw"].resample("1D").sum(min_count=1) * 0.25,
            "expected_kwh": df["expected_kw"].resample("1D").sum(min_count=1) * 0.25,
            "coverage": df["ac_power_kw"].resample("1D").count() / 96,
        }
    )
    daily["pi"] = daily["actual_kwh"] / daily["expected_kwh"].where(
        daily["expected_kwh"] > 0
    )
    return daily


def add_flags(daily: pd.DataFrame) -> pd.DataFrame:
    daily = daily.copy()
    daily["pi"] = daily["pi"].where(
        daily["coverage"] >= SITE.coverage_min
    )  # exclude days missing >20% of intervals
    # ignore flagged days in the pi_baseline
    flagged = pd.Series(False, index=daily.index)
    for _ in range(2):
        baseline = (
            daily["pi"]
            .where(~flagged)
            .shift(1)
            .rolling(SITE.window, min_periods=SITE.window // 2)
            .median()
        )
        flagged = daily["pi"] < SITE.flag_threshold * baseline

    daily["pi_baseline"] = baseline
    daily["flagged"] = flagged
    return daily
