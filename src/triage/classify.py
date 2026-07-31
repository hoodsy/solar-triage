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
    WEATHER = "weather"
    SNOW = "snow"
    SNOW_SHEDDING = "snow_shedding"
    CLOUD_INTERMITTENT = "cloud_intermittent"
    THERMAL = "thermal"
    DATA_GAP = "data_gap"
    UNCLASSIFIED = "unclassified"
    # referee-attribution vocabulary — the classifier never emits this;
    # it exists so resolve() on sub-metered sites shares the same enum.
    # (MIXED is gone: underexplained days now carry a primary label for the
    # fleet-wide residual plus label_2="outage" for the divergent share.)
    CURTAILMENT = "curtailment"


def per_hour(site: SiteConfig) -> float:
    """Intervals per hour on this site's grid (4.0 at 15 min)."""
    return pd.Timedelta("1h") / pd.Timedelta(site.interval)


def day_slice(df: pd.DataFrame, day: pd.Timestamp) -> pd.DataFrame:
    """One calendar day of intraday rows; empty frame for fully-silent days."""
    try:
        return df.loc[day.strftime("%Y-%m-%d")]
    except KeyError:  # coverage-0 day: no rows at all
        return df.iloc[0:0]


# weather-tier thresholds, tuned 2026-07 on sn120 flagged days vs 2107 referee
# fault days (chop_mad: broken cloud 0.18 median vs real-fault 0.055 median)
CSR_WEATHER = 0.75  # below: meaningfully less sun than a clear day
CSR_RAINY = 0.65  # below + measurable rain: dim enough that rain explains it
CSR_DIM = 0.50  # below + smooth: overcast deeper than any model error
# (tuned up from 0.30 on referee sweep 2026-07: smooth rainy days at csr ~0.6
# were falling through to pi-step and claiming false outages)
CHOP_BROKEN_SKY = 0.10  # hourly ratio sawtooth threshold
RAIN_MM = 1.0  # daily precip to call a day rainy
QUANT_TOL = 0.15  # units: how close a deficit must land to an integer step
CEILING_FRAC = 0.95  # within this of ac_capacity = "at the AC ceiling"
LIT_FRAC = 0.20  # expected above this share of dc_capacity = "lit hours"

# run thresholds in HOURS (converted per site via per_hour). The values were
# tuned on 15-minute 2107 referee data; re-tune before trusting a coarser grid.
DEAD_RUN_H = 1.0  # dead-run rule: actual <5% of expected this long
PARTIAL_PLATEAU_H = 1.75  # real degraded ceilings held >= 1.75h
CLIP_PLATEAU_H = 2.0  # pinned at the true ceiling this long = clipping


def unit_deficit(deficit_kw: float, site: SiteConfig) -> tuple[float, float]:
    """Deficit in units of one inverter/string; distance to the nearest whole
    unit. Real partial loss lands on an integer; fleet-uniform effects don't."""
    unit = site.ac_capacity_kw / site.n_units
    units = deficit_kw / unit
    return units, abs(units - round(units))


def quantized(deficit_kw: float, site: SiteConfig) -> str:
    """Evidence suffix: how the deficit sits on the -k/N unit grid."""
    if site.n_units <= 1:
        return ""
    units, _ = unit_deficit(deficit_kw, site)
    return (
        f" ≈ {round(units)} of {site.n_units} units out (deficit {units:.1f} units)"
    )


def day_csr(intraday: pd.DataFrame) -> float:
    """Day's actual energy vs the cloudless ceiling; NaN without clearsky."""
    if "clearsky_kw" not in intraday.columns:
        return float("nan")
    ceiling = intraday["clearsky_kw"].sum()
    return intraday["ac_power_kw"].sum() / ceiling if ceiling > 0 else float("nan")


def hourly_ratio(intraday: pd.DataFrame, site: SiteConfig) -> pd.Series:
    """Hourly actual/expected over lit hours — the shape-mismatch series."""
    lit = intraday[intraday["expected_kw"] > LIT_FRAC * site.dc_capacity_kw]
    hourly = lit.resample("1h").mean()
    return (hourly["ac_power_kw"] / hourly["expected_kw"]).dropna()


def chop_mad(intraday: pd.DataFrame, site: SiteConfig) -> float:
    """Median absolute hour-to-hour delta of the ratio: sustained sawtooth =
    broken cloud; a real derate scales smoothly. Median, not std — one frontal
    regime change must not read as chop."""
    deltas = hourly_ratio(intraday, site).diff().abs().dropna()
    return float(deltas.median()) if len(deltas) else 0.0


def longest_run(mask: pd.Series) -> int:
    """Length of the longest consecutive run of True."""
    blocks = (~mask).cumsum()  # each False starts a new block
    return int(mask.groupby(blocks).sum().max() or 0)


def midday_plateau(intraday: pd.DataFrame) -> tuple[int, float, pd.DataFrame]:
    """Longest 10:00-14:00 run within 3% of the day's peak; returns (run, peak_kw, midday)."""
    peak = intraday["ac_power_kw"].max()
    midday = intraday.between_time("10:00", "14:00")
    return longest_run(midday["ac_power_kw"] > 0.97 * peak), peak, midday


def detect_dead(
    day: pd.Timestamp, intraday: pd.DataFrame, daily: pd.DataFrame, site: SiteConfig
) -> str | None:
    actual, expected = intraday["ac_power_kw"], intraday["expected_kw"]
    dead = (actual < 0.05 * expected) & (expected > LIT_FRAC * site.dc_capacity_kw)
    run = longest_run(dead)
    if run >= DEAD_RUN_H * per_hour(site):
        return (
            f"actual <5% of expected for {run} consecutive intervals "
            f"(~{run / per_hour(site):.1f}h) with expected >20% of capacity"
        )
    return None


# snow thresholds, set on the 2026-07 bucket study (705 days across
# 1239/1433/1283: pi median 0.01, tmax median -0.5 °C, fresh trailing snow)
SNOW_3D_CM = 1.0  # trailing 3-day snowfall that can bury a panel
SNOW_7D_CM = 5.0  # or a heavier week: lingering cover outlasts the storm
SNOW_30D_CM = 10.0  # standing pack: a heavy month lingers past the 7d window
SNOW_TMAX_C = 5.0  # above this the cover melts off same-day
SNOW_SHED_TMAX_C = 12.0  # partial cover survives milder days while shedding
SNOW_PI = 0.6  # burial suppresses deeply — mild dips are not snow


def detect_snow(
    day: pd.Timestamp, intraday: pd.DataFrame, daily: pd.DataFrame, site: SiteConfig
) -> str | None:
    """Panel burial: fresh or accumulated snowfall + cold + deep collapse.
    Runs ahead of the outage rules — after a storm, burial is the likelier
    story than hardware, and the meter cannot tell them apart anyway. Sites
    without a snow_cm stream (no Open-Meteo met join) never match."""
    if "snow_cm" not in daily.columns:
        return None
    snow3 = daily.loc[:day, "snow_cm"].tail(3).sum()
    snow7 = daily.loc[:day, "snow_cm"].tail(7).sum()
    if not (snow3 >= SNOW_3D_CM or snow7 >= SNOW_7D_CM):
        return None
    pi = daily.at[day, "pi"]
    if not pi < SNOW_PI:  # NaN-safe
        return None
    tmax = (
        intraday["temp_c"].max() if "temp_c" in intraday.columns else float("nan")
    )
    if tmax >= SNOW_TMAX_C:  # NaN tmax passes: a gap day shouldn't veto snow
        return None
    tmax_txt = f"day max {tmax:.0f} °C" if pd.notna(tmax) else "no temp reading"
    return (
        f"PI {pi:.2f} with {snow3:.1f} cm snow in 3 days ({snow7:.1f} cm in 7) "
        f"and {tmax_txt} — panel burial, not hardware"
    )


def detect_snow_shedding(
    day: pd.Timestamp, intraday: pd.DataFrame, daily: pd.DataFrame, site: SiteConfig
) -> str | None:
    """Partial snow cover melting or sliding off: suppressed but not buried.
    Sits BELOW the structural rules — a bright-day plateau or dead run in a
    snowy week is still hardware — and takes only what they left."""
    if "snow_cm" not in daily.columns:
        return None
    snow7 = daily.loc[:day, "snow_cm"].tail(7).sum()
    snow30 = daily.loc[:day, "snow_cm"].tail(30).sum()
    if not (snow7 >= SNOW_3D_CM or snow30 >= SNOW_30D_CM):
        return None
    pi = daily.at[day, "pi"]
    if not pi < 0.95:  # NaN-safe; hard burial (< SNOW_PI) went to snow above
        return None
    tmax = (
        intraday["temp_c"].max() if "temp_c" in intraday.columns else float("nan")
    )
    if tmax >= SNOW_SHED_TMAX_C:
        return None
    tmax_txt = f"day max {tmax:.0f} °C" if pd.notna(tmax) else "no temp reading"
    return (
        f"PI {pi:.2f} with {snow7:.1f} cm snow in 7 days ({snow30:.1f} cm in 30) "
        f"and {tmax_txt} — partial cover shedding off panels"
    )


CSR_BRIGHT = 0.90  # above this the sky story runs out entirely


def detect_cloud_intermittent(
    day: pd.Timestamp, intraday: pd.DataFrame, daily: pd.DataFrame, site: SiteConfig
) -> str | None:
    """Bright but changeable: passing clouds the reanalysis mistimed, costing
    a mild deficit. Model-tier sites only — with a POA sensor the clouds
    cancel out of PI and ratio chop means hardware, exactly as in
    detect_weather. Dimmer chop (csr < 0.75) is detect_weather's broken-sky
    branch; this rule takes the bright remainder."""
    if "poa_wm2" in intraday.columns:
        return None
    csr = day_csr(intraday)
    if not (CSR_WEATHER <= csr < CSR_BRIGHT):  # NaN-safe
        return None
    if chop_mad(intraday, site) <= CHOP_BROKEN_SKY:
        return None
    pi = daily.at[day, "pi"]
    if not pi >= 0.7:  # deep loss under sawtooth is a fault story, not sky
        return None
    return (
        f"bright but changeable — output {csr:.0%} of clear-sky ceiling, "
        f"hourly ratio chopping ±{chop_mad(intraday, site):.2f}, PI {pi:.2f} "
        f"— cloud timing the model missed"
    )


TMAX_HOT_C = 32.0  # a thermal story needs a hot day
TEMP_CORR = -0.6  # hourly ratio must track temperature down


def detect_thermal(
    day: pd.Timestamp, intraday: pd.DataFrame, daily: pd.DataFrame, site: SiteConfig
) -> str | None:
    """Fleet-wide midday sag that tracks the temperature curve. Yields to the
    outage branches when the deficit lands on a -k/N step: thermal derate hits
    every inverter together, so it lands between the steps."""
    if "temp_c" not in intraday.columns or intraday["temp_c"].isna().all():
        return None
    tmax = intraday["temp_c"].max()
    if tmax < TMAX_HOT_C:
        return None
    ratio = hourly_ratio(intraday, site)
    if len(ratio) < 5:
        return None
    temp = intraday["temp_c"].resample("1h").mean().reindex(ratio.index)
    corr = ratio.corr(temp)
    if not corr < TEMP_CORR:  # NaN-safe
        return None
    bright = intraday[intraday["expected_kw"] > 0.5 * site.ac_capacity_kw]
    if bright.empty:
        return None
    deficit = (bright["expected_kw"] - bright["ac_power_kw"]).median()
    units, _ = unit_deficit(deficit, site)
    # quantization only discriminates below one unit: any deficit big enough
    # to contain a whole dead inverter is ambiguous from the meter alone, so
    # it defers to the outage branches (referee sweep 2026-07: mixed hot days
    # with inv_14 dead measured 2.5-4.2 units and must stay outage)
    if site.n_units > 1 and units >= 1 - QUANT_TOL:
        return None
    return (
        f"midday sag tracking {tmax:.0f} °C afternoon (ratio↔temp r={corr:.2f}), "
        f"deficit {units:.1f}/{site.n_units} units — thermal derate, not capacity loss"
    )


def detect_partial(
    day: pd.Timestamp, intraday: pd.DataFrame, daily: pd.DataFrame, site: SiteConfig
) -> str | None:
    # partial outage, same-day: bright-day plateau at a degraded ceiling —
    # the surviving inverters maxing out well below the plant's AC capacity
    plateau_run, peak, midday = midday_plateau(intraday)
    if (
        plateau_run >= PARTIAL_PLATEAU_H * per_hour(site)
        and peak < CEILING_FRAC * site.ac_capacity_kw
        and midday["expected_kw"].max() > CEILING_FRAC * site.ac_capacity_kw  # bright
    ):
        return (
            f"bright-day output plateaued {plateau_run / per_hour(site):.1f}h at {peak:.0f} kW — "
            f"{peak / site.ac_capacity_kw:.0%} of the {site.ac_capacity_kw:.0f} kW "
            f"AC ceiling — partial capacity loss"
            + quantized(site.ac_capacity_kw - peak, site)
        )
    # partial outage without a clean plateau (cloud-chopped mornings, short caps):
    # healthy panels keep the cool-morning surplus while midday capacity is missing
    lit = intraday[intraday["expected_kw"] > LIT_FRAC * site.dc_capacity_kw]
    ratio = lit["ac_power_kw"] / lit["expected_kw"]
    morning = ratio.between_time("07:00", "10:00").median()
    midday_ratio = ratio.between_time("11:00", "14:00").median()
    if morning > 1.15 and midday_ratio < 0.92:  # tuned on 2024 referee data
        return (
            f"morning output {morning:.0%} of expected but midday only "
            f"{midday_ratio:.0%} — capacity missing at high sun, panels healthy"
            + quantized((1 - midday_ratio) * site.ac_capacity_kw, site)
        )
    return None


def detect_pi_step(
    day: pd.Timestamp, intraday: pd.DataFrame, daily: pd.DataFrame, site: SiteConfig
) -> str | None:
    recent = daily.loc[:day, "pi"].tail(3)
    if (
        len(recent) == 3
        and (recent < site.flag_threshold * daily.at[day, "pi_baseline"]).all()
    ):
        return (
            f"PI {recent.median():.2f} vs baseline {daily.at[day, 'pi_baseline']:.2f} "
            f"for 3+ consecutive days — persistent step; partial loss and "
            f"uniform curtailment/drift both fit (sub-metering would resolve)"
        )
    return None


def detect_weather(
    day: pd.Timestamp, intraday: pd.DataFrame, daily: pd.DataFrame, site: SiteConfig
) -> str | None:
    """Model-missed clouds, not hardware. Two paths: broken sky (sawtooth
    ratio, well under the clear ceiling) and uniformly dark rain. csr guards
    the label from bright-day faults; NaN csr (sensor site) disables the rule."""
    if "poa_wm2" in intraday.columns:
        # measured-POA site: clouds cancel out of actual/expected, so a
        # "model-missed clouds" story cannot occur — ratio chop there is
        # hardware churn (9069: 28 of 33 weather labels were inverter trips)
        return None
    csr = day_csr(intraday)
    if not csr < CSR_WEATHER:  # NaN-safe: no clearsky column -> never weather
        return None
    rain = (
        daily.at[day, "rain_mm"]
        if "rain_mm" in daily.columns and pd.notna(daily.at[day, "rain_mm"])
        else 0.0
    )
    chop = chop_mad(intraday, site)
    if chop > CHOP_BROKEN_SKY:
        tag = f"; {rain:.1f} mm rain" if rain >= RAIN_MM else ""
        return (
            f"changeable-sky day — output {csr:.0%} of clear-sky ceiling, "
            f"hourly output/expected chopping ±{chop:.2f}{tag}"
        )
    if csr < CSR_RAINY and rain >= RAIN_MM:
        return (
            f"dim rain day — output {csr:.0%} of clear-sky ceiling, "
            f"{rain:.1f} mm rain"
        )
    # deep smooth overcast, no rain required: at half the clear ceiling the
    # sky itself is the explanation — reanalysis under-calls cloud depth on
    # these days (728 unclassified at csr med 0.48 / chop med 0.044 in the
    # 2026-07 bucket study). Guard: the MODEL must also have seen cloud
    # (expected well under clearsky) — csr is actual/ceiling, so a smooth
    # fault on a bright day is equally dim by csr alone, and only the
    # model's own cloud factor separates the two stories.
    ceiling = intraday["clearsky_kw"].sum()
    model_csr = intraday["expected_kw"].sum() / ceiling if ceiling > 0 else 1.0
    if csr < CSR_DIM and model_csr < CSR_WEATHER:
        return (
            f"deep overcast — output {csr:.0%} of clear-sky ceiling with the "
            f"model itself at {model_csr:.0%}, smooth hourly ratio "
            f"(chop ±{chop:.2f}); model missed cloud depth"
        )
    return None


def detect_clipping(
    day: pd.Timestamp, intraday: pd.DataFrame, daily: pd.DataFrame, site: SiteConfig
) -> str | None:
    plateau_run, peak, midday = midday_plateau(intraday)
    if (
        plateau_run >= CLIP_PLATEAU_H * per_hour(site)
        and peak >= CEILING_FRAC * site.ac_capacity_kw  # pinned at the real ceiling
        and midday["expected_kw"].max() > 1.05 * peak
    ):
        return (
            f"actual pinned {plateau_run / per_hour(site):.1f}h at {peak:.0f} kW — the "
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


# precedence order — first match wins. Structural signatures always beat
# trailing-context ones: a dead day in the rain is still dead, but "3 low
# days in a row" is also what a cloud spell looks like (weather slots in
# ahead of detect_pi_step; thermal ahead of detect_partial).
# detect_pi_step labels UNCLASSIFIED on purpose: a persistent daily-PI step
# equally fits partial loss and fleet-uniform curtailment/drift, and no
# meter-level signal separates them (9069 referee: 74 of 271 step claims
# had zero divergent inverters, with chop and depth distributions identical
# to the confirmed ones) — the evidence string carries what is known.
RULES = [
    # snow leads the fault rules: a buried panel also trips the dead-run
    # test (the model still expects power), and after a storm burial is the
    # likelier story — the meter cannot separate them, the snowfall can
    (Fault.SNOW, detect_snow),
    (Fault.OUTAGE, detect_dead),
    (Fault.THERMAL, detect_thermal),
    (Fault.OUTAGE, detect_partial),
    (Fault.CLIPPING, detect_clipping),
    (Fault.WEATHER, detect_weather),
    (Fault.SNOW_SHEDDING, detect_snow_shedding),
    (Fault.CLOUD_INTERMITTENT, detect_cloud_intermittent),
    (Fault.UNCLASSIFIED, detect_pi_step),
    (Fault.SOILING, detect_soiling),
]


def precedence() -> list[str]:
    """Rule precedence as label names, derived so report text can't go stale.
    data_gap leads: it is the pre-rule gate in classify_day."""
    return [str(Fault.DATA_GAP), *dict.fromkeys(str(label) for label, _ in RULES)]


def classify_day(
    day: pd.Timestamp, intraday: pd.DataFrame, daily: pd.DataFrame, site: SiteConfig
) -> tuple[Fault, str]:
    # data quality precedes fault inference: no rule runs on a day we can't see
    coverage = daily.at[day, "coverage"]
    if coverage < site.coverage_min:
        return Fault.DATA_GAP, (
            f"only {coverage:.0%} of intervals judgeable — "
            f"meter or sensor gap, performance unknown"
        )
    for label, detect in RULES:
        if evidence := detect(day, intraday, daily, site):
            return label, evidence
    return Fault.UNCLASSIFIED, "no rule matched"


def events(result: pd.DataFrame, daily: pd.DataFrame, site: SiteConfig) -> pd.DataFrame:
    """Merge calendar-consecutive same-label days into events. data_gap days
    bridge same-label neighbors (a comms dropout must not split one outage in
    two); a healthy day does split. Deficit sums valid-coverage days only."""
    columns = ["label", "start", "end", "days", "median_pi",
               "energy_deficit_kwh", "evidence"]
    if result.empty:
        return pd.DataFrame(columns=columns)
    segs = []  # strictly-consecutive same-label runs
    for date, row in result.sort_index().iterrows():
        prev = segs[-1] if segs else None
        if (
            prev is not None
            and row["label"] == prev["label"]
            and (date - prev["end"]).days == 1
        ):
            prev["end"] = date
        else:
            segs.append(
                {"label": row["label"], "start": date, "end": date,
                 "evidence": row["evidence"]}
            )
    merged = []  # bridge label/gap/label triples
    for seg in segs:
        if (
            len(merged) >= 2
            and merged[-1]["label"] == Fault.DATA_GAP
            and merged[-2]["label"] == seg["label"]
            and (seg["start"] - merged[-1]["end"]).days == 1
            and (merged[-1]["start"] - merged[-2]["end"]).days == 1
        ):
            merged.pop()
            merged[-1]["end"] = seg["end"]
        else:
            merged.append(seg)
    rows = []
    for seg in merged:
        span = daily.loc[seg["start"] : seg["end"]]
        valid = span[span["coverage"] >= site.coverage_min]
        rows.append(
            {
                "label": seg["label"],
                "start": seg["start"].date(),
                "end": seg["end"].date(),
                "days": (seg["end"] - seg["start"]).days + 1,
                "median_pi": result.loc[seg["start"] : seg["end"], "pi"].median(),
                "energy_deficit_kwh": (
                    valid["expected_kwh"] - valid["actual_kwh"]
                ).sum(),
                "evidence": seg["evidence"],
            }
        )
    return pd.DataFrame(rows, columns=columns)


def classify(daily: pd.DataFrame, df: pd.DataFrame, site: SiteConfig) -> pd.DataFrame:
    """
    For each flagged day, select it and the trailing daily context,
    run rules in precedence order, first match wins.
    """
    rows = []
    for day in daily.index[daily["flagged"].fillna(False)]:
        label, evidence = classify_day(day, day_slice(df, day), daily, site)
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
