import pandas as pd

from triage.config import SiteConfig


def clearsky_poa(index: pd.DatetimeIndex, site: SiteConfig) -> pd.Series:
    """Clear-sky plane-of-array irradiance for sites without a POA sensor.

    This is a *ceiling*, not a forecast: unlike measured POA, clouds do not
    cancel out of PI for clear-sky sites, so their PI is weather-noisy and
    flag thresholds need per-site retuning.
    """
    import pvlib  # imported lazily: measured-POA sites never pay for it

    location = pvlib.location.Location(site.lat, site.lon, tz=site.tz)
    solpos = location.get_solarposition(index)
    clearsky = location.get_clearsky(index)
    total = pvlib.irradiance.get_total_irradiance(
        surface_tilt=site.tilt,
        surface_azimuth=site.azimuth,
        solar_zenith=solpos["apparent_zenith"],
        solar_azimuth=solpos["azimuth"],
        dni=clearsky["dni"],
        ghi=clearsky["ghi"],
        dhi=clearsky["dhi"],
    )
    return total["poa_global"]


def build_dataset(site: SiteConfig) -> pd.DataFrame:
    df = site.source.load(site)
    if "poa_wm2" in df.columns and df["poa_wm2"].notna().any():
        poa = df["poa_wm2"]  # measured irradiance: weather cancels out of PI
    else:
        poa = clearsky_poa(df.index, site)
    df["expected_kw"] = site.dc_capacity_kw * (poa / 1000.0) * site.derate
    return df


def build_daily(df: pd.DataFrame, site: SiteConfig) -> pd.DataFrame:
    hours = pd.Timedelta(site.interval) / pd.Timedelta("1h")  # 0.25 for 15min
    per_day = pd.Timedelta("1D") / pd.Timedelta(site.interval)  # 96.0 for 15min
    daily = pd.DataFrame(
        {
            "actual_kwh": df["ac_power_kw"].resample("1D").sum(min_count=1) * hours,
            "expected_kwh": df["expected_kw"].resample("1D").sum(min_count=1) * hours,
            "coverage": df["ac_power_kw"].resample("1D").count() / per_day,
        }
    )
    daily["pi"] = daily["actual_kwh"] / daily["expected_kwh"].where(
        daily["expected_kwh"] > 0
    )
    return daily


def add_flags(daily: pd.DataFrame, site: SiteConfig) -> pd.DataFrame:
    daily = daily.copy()
    daily["pi"] = daily["pi"].where(
        daily["coverage"] >= site.coverage_min
    )  # exclude days missing >20% of intervals
    # ignore flagged days in the pi_baseline
    flagged = pd.Series(False, index=daily.index)
    for _ in range(2):
        baseline = (
            daily["pi"]
            .where(~flagged)
            .shift(1)
            .rolling(site.window, min_periods=site.window // 2)
            .median()
        )
        flagged = daily["pi"] < site.flag_threshold * baseline

    daily["pi_baseline"] = baseline
    daily["flagged"] = flagged
    return daily
