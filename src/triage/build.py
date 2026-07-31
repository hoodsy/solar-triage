import pandas as pd

from triage.config import SiteConfig
from triage.physics import clearsky_poa, expected_kw


def build_dataset(site: SiteConfig) -> pd.DataFrame:
    df = site.source.load(site)
    # trust ladder for the irradiance driving expected power:
    if "poa_wm2" in df.columns and df["poa_wm2"].notna().any():
        poa = df["poa_wm2"]  # 1. on-site sensor: weather cancels out of PI
    elif site.weather is not None:
        poa = site.weather.poa(site).reindex(df.index)  # 2. reanalysis clouds
    else:
        poa = clearsky_poa(df.index, site)  # 3. cloudless ceiling
    df["expected_kw"] = expected_kw(poa, site)
    # the cloudless ceiling, kept alongside expected: weather rules compare
    # "how much sun arrived" (csr) independently of what the model believed
    if None not in (site.lat, site.lon, site.tilt, site.azimuth):
        df["clearsky_kw"] = expected_kw(clearsky_poa(df.index, site), site)
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
    # ignore flagged days in the pi_baseline; iterate to a fixpoint — excluding
    # flagged (low) days only ever raises the median, so this converges. Two
    # passes are not enough for outages longer than ~half a window.
    flagged = pd.Series(False, index=daily.index)
    for _ in range(12):
        baseline = (
            daily["pi"]
            .where(~flagged)
            .shift(1)
            .rolling(site.window, min_periods=site.window // 2)
            .median()
            .ffill()  # window ran dry (long outage): hold last good baseline
        )
        new = daily["pi"] < site.flag_threshold * baseline
        if new.equals(flagged):
            break
        flagged = new

    # comms loss is reportable, not just excludable: flag low-coverage days
    # (their pi stays masked, so they never feed the baseline)
    flagged = flagged | (daily["coverage"] < site.coverage_min)

    daily["pi_baseline"] = baseline
    daily["flagged"] = flagged
    return daily


def build(site: SiteConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The frame pipeline: canonical interval frame + flagged daily frame."""
    df = build_dataset(site)
    daily = build_daily(df, site).loc[site.report_start : site.report_end]
    daily = add_flags(daily, site)
    return df, daily
