"""Per-day feature vector for training: the measurements the rules read,
written down as numbers.

Each day compresses to the checklist an expert fills in from the daily
curve — brightness vs the clear ceiling, jaggedness, plateau length,
temperature tracking, snow trail, trailing PI slope. Everything is a
ratio or a fraction of plant capacity so a 2 kW roof and a 38 MW farm
live on the same scale, and everything is computable on the edge from
the site's own streams. NaN means "not measurable here" (no temp sensor,
short history), never zero.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from triage.classify import (
    LIT_FRAC,
    chop_mad,
    day_csr,
    hourly_ratio,
    longest_run,
    midday_plateau,
    per_hour,
    unit_deficit,
)

if TYPE_CHECKING:
    from triage.config import SiteConfig

FEATURE_COLUMNS = [
    "pi_rel", "csr", "model_csr", "chop",
    "plateau_run_h", "peak_frac", "expected_peak_frac", "dead_run_h",
    "morning_ratio", "midday_ratio", "tmax_c", "temp_corr",
    "snow_3d", "snow_7d", "snow_30d",
    "pi_slope_14d", "pi_drop_share",
    "unit_count", "unit_dist",
    "doy_sin", "doy_cos",
]
# (pi, pi_baseline, coverage, rain_mm already live in the export's daily block)


def day_features(
    day: pd.Timestamp, intraday: pd.DataFrame, daily: pd.DataFrame, site: SiteConfig
) -> dict[str, float]:
    nan = float("nan")
    f = dict.fromkeys(FEATURE_COLUMNS, nan)

    doy = day.dayofyear
    f["doy_sin"] = math.sin(2 * math.pi * doy / 365.25)
    f["doy_cos"] = math.cos(2 * math.pi * doy / 365.25)

    pi = daily.at[day, "pi"]
    baseline = daily.at[day, "pi_baseline"] if "pi_baseline" in daily.columns else nan
    if pd.notna(pi) and pd.notna(baseline) and baseline > 0:
        f["pi_rel"] = pi / baseline

    if "snow_cm" in daily.columns:
        trail = daily.loc[:day, "snow_cm"]
        f["snow_3d"] = trail.tail(3).sum()
        f["snow_7d"] = trail.tail(7).sum()
        f["snow_30d"] = trail.tail(30).sum()

    # soiling internals: trailing-14 PI slope and step-vs-trend share
    trail_pi = daily.loc[:day, "pi"].iloc[:-1].dropna().tail(14)
    if len(trail_pi) >= 10:
        f["pi_slope_14d"] = float(
            np.polyfit(np.arange(len(trail_pi)), trail_pi.to_numpy(), 1)[0]
        )
        total = trail_pi.iloc[0] - trail_pi.iloc[-1]
        deltas = trail_pi.diff().dropna()
        if total > 0 and len(deltas):
            f["pi_drop_share"] = float(-deltas.min() / total)

    if intraday.empty:
        return f

    f["csr"] = day_csr(intraday)
    if "clearsky_kw" in intraday.columns:
        ceiling = intraday["clearsky_kw"].sum()
        if ceiling > 0:
            f["model_csr"] = intraday["expected_kw"].sum() / ceiling
    f["chop"] = chop_mad(intraday, site)

    run, peak, midday = midday_plateau(intraday)
    f["plateau_run_h"] = run / per_hour(site)
    f["peak_frac"] = peak / site.ac_capacity_kw
    if len(midday):
        f["expected_peak_frac"] = midday["expected_kw"].max() / site.ac_capacity_kw

    actual, expected = intraday["ac_power_kw"], intraday["expected_kw"]
    dead = (actual < 0.05 * expected) & (expected > LIT_FRAC * site.dc_capacity_kw)
    f["dead_run_h"] = longest_run(dead) / per_hour(site)

    lit = intraday[intraday["expected_kw"] > LIT_FRAC * site.dc_capacity_kw]
    if len(lit):
        ratio = lit["ac_power_kw"] / lit["expected_kw"]
        f["morning_ratio"] = ratio.between_time("07:00", "10:00").median()
        f["midday_ratio"] = ratio.between_time("11:00", "14:00").median()

    if "temp_c" in intraday.columns and intraday["temp_c"].notna().any():
        f["tmax_c"] = intraday["temp_c"].max()
        hr = hourly_ratio(intraday, site)
        if len(hr) >= 5:
            temp = intraday["temp_c"].resample("1h").mean().reindex(hr.index)
            f["temp_corr"] = hr.corr(temp)

    # how the bright-hours deficit sits on the -k/N unit grid
    bright = intraday[intraday["expected_kw"] > 0.5 * site.ac_capacity_kw]
    if len(bright) and site.n_units > 1:
        deficit = (bright["expected_kw"] - bright["ac_power_kw"]).median()
        units, dist = unit_deficit(deficit, site)
        f["unit_count"] = units
        f["unit_dist"] = dist

    return f
