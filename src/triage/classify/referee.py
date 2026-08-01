"""Referee: per-inverter fleet-relative grading for sites with sub-metering.

The classifier sees only the meter + a weather model; the referee sees the
per-inverter breakdown those never touch. Fleet-relative comparison cancels
everything fleet-uniform (weather, soiling, thermal, curtailment) — so it
confirms per-inverter claims and refutes false ones, but is blind to uniform
events BY DESIGN: it can falsify a thermal label, never confirm one.

resolve() is the single grading pass. Every flagged day keeps or upgrades its
label and carries a verdict: confirmed/refuted where the fleet can grade the
classifier's claim, attributed where it resolves an honest unclassified,
uncheckable otherwise (data_gap claims unjudgeability and is never graded).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from triage.classify import (
    CEILING_FRAC,
    CSR_WEATHER,
    Fault,
    day_csr,
    day_slice,
    midday_plateau,
    per_hour,
)

if TYPE_CHECKING:
    from triage.config import SiteConfig

DIVERGENCE_MARGIN = 0.10  # an inverter this far under the fleet median diverges
FLEET_HEALTHY = 0.5  # only judge days the fleet itself produced meaningfully
TRAIL_DAYS = 30  # per-inverter normalization window
SHARE_DOMINANT = 0.5  # divergent inverters explaining this much own the day
CURTAIL_PLATEAU_H = 1.5  # bright flat clamp this long with a healthy fleet


def daily_divergence(inv_kw: pd.DataFrame) -> pd.DataFrame:
    """Per day: which inverters fell DIVERGENCE_MARGIN under the fleet median,
    after normalizing each inverter by its own trailing median (cancels fixed
    size/orientation differences between inverters)."""
    step = inv_kw.index[1] - inv_kw.index[0]
    daily = inv_kw.resample("1D").sum() * (step / pd.Timedelta("1h"))  # kWh
    trail = daily.rolling(TRAIL_DAYS, min_periods=TRAIL_DAYS // 3).median().shift(1)
    norm = daily / trail
    fleet = norm.median(axis=1)
    judgeable = fleet > FLEET_HEALTHY
    divergent = norm.lt((1 - DIVERGENCE_MARGIN) * fleet, axis=0).where(
        judgeable, False
    )
    # attribution: the share of the plant's shortfall (vs trailing norms) the
    # divergent inverters explain BEYOND the fleet-wide level. On a cloudy day
    # with one dead inverter the clouds dominate and the share is tiny; on a
    # clear day the dead inverter is the whole story and the share is ~1.
    expected = trail.mul(fleet, axis=0)  # fleet-scaled per-inverter expectation
    div_short = (expected - daily).clip(lower=0).where(divergent, 0.0).sum(axis=1)
    plant_short = (trail - daily).clip(lower=0).sum(axis=1)
    return pd.DataFrame(
        {
            "n_divergent": divergent.sum(axis=1).astype(int),
            "divergent": divergent.apply(lambda r: list(r.index[r]), axis=1),
            "fleet_median": fleet,
            "div_share": (div_short / plant_short).where(plant_short > 0),
        }
    )


def resolve(
    result: pd.DataFrame,
    ref: pd.DataFrame,
    site: SiteConfig,
    df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Final labels + verdicts: classifier output refined by the fleet channel.

    Labels the classifier could defend stand and get graded (outage wants
    divergence — or total collapse, which has zero divergence by definition;
    thermal/weather are refuted only when divergent inverters own the day's
    shortfall). Its honest `unclassified` days get attributed: inverter-subset
    outage, plant-wide collapse, or curtailment (bright flat clamp, zero
    divergence — needs `df` for the intraday shape). Underexplained days —
    some divergence but the fleet-wide residual dominates — get a primary
    label for the residual (weather / curtailment via the intraday shape,
    else unclassified) with label_2="outage" for the divergent share; the
    MIXED bucket this replaces hid exactly that split. The residual check
    requires a real positive share: div_share is NaN when the plant was not
    short at daily energy at all, and "loss plus something fleet-wide" was
    unjustified there (135 of 370 mixed labels were that artifact).
    """
    if result.empty:
        return pd.DataFrame(
            columns=[*result.columns, "label_2", "verdict"], index=result.index
        )
    rows = []
    for day, row in result.iterrows():
        key = day.normalize()
        label, why = row["label"], row["evidence"]
        label_2 = None
        verdict = "uncheckable"
        if key in ref.index and pd.notna(ref.at[key, "fleet_median"]):
            n = ref.at[key, "n_divergent"]
            share = ref.at[key, "div_share"]
            fleet = ref.at[key, "fleet_median"]
            faulty = n >= 1 and pd.notna(share) and share >= SHARE_DOMINANT
            collapsed = fleet <= FLEET_HEALTHY
            if label == Fault.OUTAGE:
                verdict = "confirmed" if n >= 1 or collapsed else "refuted"
            elif label in (
                Fault.THERMAL,
                Fault.WEATHER,
                Fault.SNOW,
                Fault.SNOW_SHEDDING,
                Fault.CLOUD_INTERMITTENT,
            ):  # fleet-uniform sky stories: refuted when a divergent
                # inverter subset owns the day's shortfall
                verdict = "refuted" if faulty else "confirmed"
            elif label == Fault.UNCLASSIFIED:
                if faulty:
                    label, verdict = Fault.OUTAGE, "attributed"
                    why = (
                        f"{n}/{site.n_units} inverters divergent, explaining "
                        f"{share:.0%} of the shortfall — was: {why}"
                    )
                elif collapsed:
                    label, verdict = Fault.OUTAGE, "attributed"
                    why = (
                        f"plant-wide: fleet at {fleet:.0%} of trailing norm "
                        f"— was: {why}"
                    )
                elif n >= 1 and pd.notna(share) and share > 0:
                    # minor loss + dominant fleet-wide residual: name the
                    # residual from the intraday shape, keep the loss as
                    # the secondary label
                    residual = Fault.UNCLASSIFIED
                    detail = ""
                    if df is not None:
                        intraday = day_slice(df, day)
                        csr = day_csr(intraday)
                        run, peak, _ = midday_plateau(intraday)
                        if csr < CSR_WEATHER:
                            residual = Fault.WEATHER
                            detail = f" (dim day: {csr:.0%} of clear ceiling)"
                        elif (
                            run >= CURTAIL_PLATEAU_H * per_hour(site)
                            and peak < CEILING_FRAC * site.ac_capacity_kw
                        ):
                            residual = Fault.CURTAILMENT
                            detail = f" (bright day clamped at {peak:.0f} kW)"
                    label, label_2, verdict = residual, Fault.OUTAGE, "attributed"
                    why = (
                        f"fleet-wide {residual}{detail} plus {n} divergent "
                        f"inverters explaining {share:.0%} — was: {why}"
                    )
                elif df is not None:
                    intraday = day_slice(df, day)
                    run, peak, _ = midday_plateau(intraday)
                    if (
                        day_csr(intraday) >= CSR_WEATHER
                        and run >= CURTAIL_PLATEAU_H * per_hour(site)
                        and peak < CEILING_FRAC * site.ac_capacity_kw
                    ):
                        label, verdict = Fault.CURTAILMENT, "attributed"
                        why = (
                            f"bright day clamped flat at {peak:.0f} kW with "
                            f"zero divergent inverters — was: {why}"
                        )
        rows.append(
            {
                "label": label,
                "label_2": label_2,
                "pi": row["pi"],
                "evidence": why,
                "verdict": verdict,
            }
        )
    return pd.DataFrame(rows, index=result.index)
