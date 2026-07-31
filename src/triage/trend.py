"""Slow-timescale layer: degradation and soiling via RdTools.

The rolling-baseline flagger is blind to standing conditions by
construction — a 0.5%/yr fade or a recurring soiling ramp is IN the
baseline. This is the instrument that sees them, run over the FULL data
span rather than the report window.

Daily PI (actual / irradiance-driven expected) is already RdTools'
"normalized energy"; year-on-year degradation and SRR soiling consume it
directly. Soiling needs measured POA — on weather-model sites the daily
PI noise (~15%) buries the soiling signal, so it is skipped.

Run: TRIAGE_SITE=<site> uv run python -m triage.trend
"""

from __future__ import annotations

import os
import warnings

import pandas as pd

from triage.build import build_daily, build_dataset
from triage.config import SITES, SiteConfig


def daily_pi(site: SiteConfig) -> tuple[pd.Series, pd.Series | None]:
    """Full-span daily PI and (when a POA sensor exists) daily insolation."""
    df = build_dataset(site)
    daily = build_daily(df, site)
    pi = (daily["pi"].where(daily["coverage"] >= site.coverage_min)).dropna()
    insolation = None
    if "poa_wm2" in df.columns:
        hours = pd.Timedelta(site.interval) / pd.Timedelta("1h")
        insolation = (df["poa_wm2"].clip(lower=0) * hours).resample("1D").sum()
    return pi, insolation


def degradation(pi: pd.Series) -> str:
    from rdtools import degradation_year_on_year

    if (pi.index[-1] - pi.index[0]).days < 730:
        return f"n/a — YoY needs 2 years, have {(pi.index[-1] - pi.index[0]).days} days"
    rd, ci, info = degradation_year_on_year(pi)
    return f"{rd:+.2f} %/yr (68% CI {ci[0]:+.2f} to {ci[1]:+.2f}, n={len(pi)} days)"


def soiling(pi: pd.Series, insolation: pd.Series | None) -> str:
    if insolation is None:
        return "n/a — needs measured POA (weather-model PI noise buries the signal)"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # rdtools.soiling is marked experimental
        from rdtools.soiling import soiling_srr

        # rdtools requires an unbroken daily index; gap days ride along as NaN
        grid = pd.date_range(pi.index[0], pi.index[-1], freq="1D", tz=pi.index.tz)
        try:
            sr, ci, info = soiling_srr(pi.reindex(grid), insolation.reindex(grid))
        except Exception as e:  # short series / no clean intervals found
            return f"n/a — {e}"
    return (
        f"insolation-weighted soiling ratio {sr:.3f} "
        f"(68% CI {ci[0]:.3f}-{ci[1]:.3f}, {len(info['soiling_interval_summary'])} intervals)"
    )


def main() -> None:
    site = SITES[os.environ.get("TRIAGE_SITE", "2107")]
    pi, insolation = daily_pi(site)
    print(f"{site.name}: {pi.index[0].date()} -> {pi.index[-1].date()} ({len(pi)} valid days)")
    print(f"degradation: {degradation(pi)}")
    print(f"soiling:     {soiling(pi, insolation)}")


if __name__ == "__main__":
    main()
