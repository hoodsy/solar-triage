from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from triage.config import SiteConfig


class Fault(StrEnum):
    OUTAGE = "outage"
    CLIPPING = "clipping"
    SOILING = "soiling"
    DATA_GAP = "data_gap"
    UNCLASSIFIED = "unclassified"


def longest_run(mask: pd.Series) -> int:
    """Length of the longest consecutive run of True."""
    blocks = (~mask).cumsum()  # each False starts a new block
    return int(mask.groupby(blocks).sum().max() or 0)


def midday_plateau(intraday: pd.DataFrame) -> tuple[int, float, pd.DataFrame]:
    """Longest 10:00-14:00 run within 3% of the day's peak; returns (run, peak_kw, midday)."""
    peak = intraday["ac_power_kw"].max()
    midday = intraday.between_time("10:00", "14:00")
    return longest_run(midday["ac_power_kw"] > 0.97 * peak), peak, midday


def detect_outage(
    day: pd.Timestamp, intraday: pd.DataFrame, daily: pd.DataFrame, site: SiteConfig
) -> str | None:
    actual, expected = intraday["ac_power_kw"], intraday["expected_kw"]
    dead = (actual < 0.05 * expected) & (expected > 0.20 * site.dc_capacity_kw)
    run = longest_run(dead)
    if run >= 4:
        return (
            f"actual <5% of expected for {run} consecutive intervals "
            f"(~{run / 4:.1f}h) with expected >20% of capacity"
        )
    # partial outage, same-day: bright-day plateau at a degraded ceiling —
    # the surviving inverters maxing out well below the plant's AC capacity
    plateau_run, peak, midday = midday_plateau(intraday)
    if (
        plateau_run >= 7  # tuned on 2024 referee data: real degraded ceilings held >=1.75h
        and peak < 0.95 * site.ac_capacity_kw
        and midday["expected_kw"].max() > 0.95 * site.ac_capacity_kw  # bright day
    ):
        return (
            f"bright-day output plateaued {plateau_run / 4:.1f}h at {peak:.0f} kW — "
            f"{peak / site.ac_capacity_kw:.0%} of the {site.ac_capacity_kw:.0f} kW "
            f"AC ceiling — partial capacity loss"
        )
    # partial outage without a clean plateau (cloud-chopped mornings, short caps):
    # healthy panels keep the cool-morning surplus while midday capacity is missing
    lit = intraday[intraday["expected_kw"] > 0.20 * site.dc_capacity_kw]
    ratio = lit["ac_power_kw"] / lit["expected_kw"]
    morning = ratio.between_time("07:00", "10:00").median()
    midday_ratio = ratio.between_time("11:00", "14:00").median()
    if morning > 1.15 and midday_ratio < 0.92:  # tuned on 2024 referee data
        return (
            f"morning output {morning:.0%} of expected but midday only "
            f"{midday_ratio:.0%} — capacity missing at high sun, panels healthy"
        )
    recent = daily.loc[:day, "pi"].tail(3)
    if (
        len(recent) == 3
        and (recent < site.flag_threshold * daily.at[day, "pi_baseline"]).all()
    ):
        return (
            f"PI {recent.median():.2f} vs baseline {daily.at[day, 'pi_baseline']:.2f} "
            f"for 3+ consecutive days — persistent step, partial loss suspected"
        )
    return None


def detect_clipping(
    day: pd.Timestamp, intraday: pd.DataFrame, daily: pd.DataFrame, site: SiteConfig
) -> str | None:
    plateau_run, peak, midday = midday_plateau(intraday)
    if (
        plateau_run >= 8
        and peak >= 0.95 * site.ac_capacity_kw  # pinned at the real ceiling
        and midday["expected_kw"].max() > 1.05 * peak
    ):
        return (
            f"actual pinned {plateau_run / 4:.1f}h at {peak:.0f} kW — the "
            f"{site.ac_capacity_kw:.0f} kW AC ceiling — while expected reached "
            f"{midday['expected_kw'].max():.0f} kW"
        )
    return None


def detect_soiling(
    day: pd.Timestamp, intraday: pd.DataFrame, daily: pd.DataFrame, site: SiteConfig
) -> str | None:
    trail = daily.loc[:day, "pi"].iloc[:-1].dropna().tail(14)  # exclude current day
    if len(trail) >= 10:
        slope = np.polyfit(np.arange(len(trail)), trail.to_numpy(), 1)[0]
        if slope < -0.003:
            deltas = trail.diff().dropna()
            total_decline = trail.iloc[0] - trail.iloc[-1]  # positive when declining
            biggest_drop = -deltas.min()  # largest one-day fall, positive
            if biggest_drop > 0.5 * total_decline:
                return None  # step disguised as a trend
            top2_drop = -deltas.nsmallest(2).sum()  # two largest one-day falls
            if top2_drop > 0.6 * total_decline:
                return None  # multiple steps disguised as a trend
            return (
                f"PI declining {slope * 100:.2f}%/day over trailing {len(trail)} days; "
                f"largest single-day drop only {biggest_drop / total_decline:.0%} of total"
            )
    return None


# NOTE: interval-count thresholds in the detectors (run >= 4, plateau_run >= 7/8,
# the "/ 4" hours math) are tuned in 15-MINUTE units on 2107 referee data.
# Re-tune before running a site with a different interval.

# precedence order — first match wins
RULES = [
    (Fault.OUTAGE, detect_outage),
    (Fault.CLIPPING, detect_clipping),
    (Fault.SOILING, detect_soiling),
]


def classify_day(
    day: pd.Timestamp, intraday: pd.DataFrame, daily: pd.DataFrame, site: SiteConfig
) -> tuple[Fault, str]:
    # data quality precedes fault inference: no rule runs on a day we can't see
    coverage = daily.at[day, "coverage"]
    if coverage < site.coverage_min:
        return Fault.DATA_GAP, (
            f"only {coverage:.0%} of intervals reported — "
            f"comms loss, production unknown"
        )
    for label, detect in RULES:
        if evidence := detect(day, intraday, daily, site):
            return label, evidence
    return Fault.UNCLASSIFIED, "no rule matched"


def classify(daily: pd.DataFrame, df: pd.DataFrame, site: SiteConfig) -> pd.DataFrame:
    """
    For each flagged day, select it and the trailing daily context,
    run rules in precedence order, first match wins.
    """
    rows = []
    for day in daily.index[daily["flagged"].fillna(False)]:
        try:
            intraday = df.loc[day.strftime("%Y-%m-%d")]
        except KeyError:  # fully-silent day (coverage 0): no intraday rows
            intraday = df.iloc[0:0]
        label, evidence = classify_day(day, intraday, daily, site)
        rows.append(
            {
                "date": day,
                "label": label,
                "pi": daily.at[day, "pi"],
                "evidence": evidence,
            }
        )
    if not rows:  # a healthy window flags nothing; keep schema AND index type
        return pd.DataFrame(
            columns=["label", "pi", "evidence"],
            index=pd.DatetimeIndex([], name="date"),
        )
    return pd.DataFrame(rows).set_index("date")
