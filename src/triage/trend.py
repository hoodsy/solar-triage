"""Slow-timescale layer: degradation and soiling via RdTools.

The rolling-baseline flagger is blind to standing conditions by
construction — a 0.5%/yr fade or a recurring soiling ramp is IN the
baseline. This is the instrument that sees them, run over the FULL data
span rather than the report window.

Daily PI (actual / irradiance-driven expected) is already RdTools'
"normalized energy"; year-on-year degradation and SRR soiling consume it
directly. Soiling needs measured POA — on weather-model sites the daily
PI noise (~15%) buries the soiling signal, so it is skipped.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from triage.config import SiteConfig


def daily_pi(daily: pd.DataFrame, site: SiteConfig) -> pd.Series:
    """Full-span daily PI, low-coverage days excluded."""
    return daily["pi"].where(daily["coverage"] >= site.coverage_min).dropna()


def daily_insolation(df: pd.DataFrame, site: SiteConfig) -> pd.Series | None:
    """Daily POA insolation when a sensor exists (soiling's weighting)."""
    if "poa_wm2" not in df.columns:
        return None
    hours = pd.Timedelta(site.interval) / pd.Timedelta("1h")
    return (df["poa_wm2"].clip(lower=0) * hours).resample("1D").sum()


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
