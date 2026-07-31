import pandas as pd

from triage.config import SiteConfig
from triage.physics import clearsky_poa, expected_kw
from triage.quality import clean


def build_dataset(site: SiteConfig) -> pd.DataFrame:
    df = site.source.load(site)
    cs_poa = (
        clearsky_poa(df.index, site)
        if None not in (site.lat, site.lon, site.tilt, site.azimuth)
        else None
    )
    # quality gate before anything derives from the sensors: masked
    # intervals become missing data and land in the data_gap machinery
    df, masked = clean(df, cs_poa)
    if masked:
        print("quality: masked " + "; ".join(f"{v} {k}" for k, v in masked.items()))
    # trust ladder for the irradiance driving expected power:
    if "poa_wm2" in df.columns and df["poa_wm2"].notna().any():
        poa = df["poa_wm2"]  # 1. on-site sensor: weather cancels out of PI
    elif site.weather is not None:
        poa = site.weather.poa(site).reindex(df.index)  # 2. reanalysis clouds
    else:
        poa = cs_poa  # 3. cloudless ceiling
    df["expected_kw"] = expected_kw(poa, site)
    # the cloudless ceiling, kept alongside expected: weather rules compare
    # "how much sun arrived" (csr) independently of what the model believed
    if cs_poa is not None:
        df["clearsky_kw"] = expected_kw(cs_poa, site)
    # met trust ladder: an on-site sensor column (temp_c) wins; Open-Meteo
    # fills whatever the adapter didn't provide
    if site.weather is not None:
        met = site.weather._met_to_grid(site.weather.met(site), site)
        cols = [c for c in met.columns if c not in df.columns]
        df = df.join(met[cols].reindex(df.index))
    return df


def build_daily(df: pd.DataFrame, site: SiteConfig) -> pd.DataFrame:
    hours = pd.Timedelta(site.interval) / pd.Timedelta("1h")  # 0.25 for 15min
    per_day = pd.Timedelta("1D") / pd.Timedelta(site.interval)  # 96.0 for 15min
    # PI compares only intervals where BOTH meter and expectation exist —
    # summing actual over a full day against expected over the valid-POA
    # half of it would inflate PI. Energy columns keep the full sums.
    both = df["ac_power_kw"].notna() & df["expected_kw"].notna()
    daily = pd.DataFrame(
        {
            "actual_kwh": df["ac_power_kw"].resample("1D").sum(min_count=1) * hours,
            "expected_kwh": df["expected_kw"].resample("1D").sum(min_count=1) * hours,
            "coverage": both.resample("1D").sum() / per_day,
            **(
                {"rain_mm": df["rain_mm"].resample("1D").sum(min_count=1)}
                if "rain_mm" in df.columns
                else {}
            ),
        }
    )
    aligned_actual = df["ac_power_kw"].where(both).resample("1D").sum(min_count=1)
    aligned_expected = df["expected_kw"].where(both).resample("1D").sum(min_count=1)
    daily["pi"] = aligned_actual / aligned_expected.where(aligned_expected > 0)
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
