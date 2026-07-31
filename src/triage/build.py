import pandas as pd

from triage.config import SiteConfig
from triage.physics import clearsky_poa, expected_kw
from triage.quality import clean


def build_dataset(site: SiteConfig) -> tuple[pd.DataFrame, dict[str, int]]:
    """Canonical interval frame + counts of quality-masked intervals."""
    df = site.source.load(site)
    cs_poa = (
        clearsky_poa(df.index, site)
        if None not in (site.lat, site.lon, site.tilt, site.azimuth)
        else None
    )
    # quality gate before anything derives from the sensors: masked
    # intervals become missing data and land in the data_gap machinery
    df, masked = clean(df, site, cs_poa)
    # daytime-only loggers (PVDAQ lake sites): an absent row with the sun
    # down is an implicit zero, not a gap — without this, coverage tops out
    # near 0.5 and every day data_gaps. Daytime absences stay NaN, so real
    # comms loss still reads as data_gap, and a no-op where nights exist.
    if cs_poa is not None:
        night = cs_poa.reindex(df.index) <= 0
        df.loc[night & df["ac_power_kw"].isna(), "ac_power_kw"] = 0.0
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
    return df, masked


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
            **{
                c: df[c].resample("1D").sum(min_count=1)
                for c in ("rain_mm", "snow_cm")
                if c in df.columns
            },
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
    #
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

    # absolute-PI guard, applied AFTER convergence and only to the output:
    # baseline-relative alone is not enough on weather-model sites —
    # reanalysis bias runs PI at 1.1-1.4 for months, the rolling median
    # follows it up (medians of 1.25 observed), and when the bias regime
    # shifts, weeks of PI≈1.0 days flag (65% of unclassified and 86% of
    # curtailment labels were this artifact, 2026-07 investigation). A day
    # that beat the model's absolute expectation is never triage-worthy.
    # The filter must NOT sit inside the loop: blocked marginal days would
    # feed the baseline, which then decays into a standing fault's level
    # and unflags whole months (2107's inv_14 era vanished that way).
    flagged = flagged & (daily["pi"] < site.pi_ceiling)

    # comms loss is reportable, not just excludable: flag low-coverage days
    # (their pi stays masked, so they never feed the baseline)
    flagged = flagged | (daily["coverage"] < site.coverage_min)

    daily["pi_baseline"] = baseline
    daily["flagged"] = flagged
    return daily


