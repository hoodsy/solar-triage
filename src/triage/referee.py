"""Referee: per-inverter fleet-relative grading for sites with sub-metering.

The classifier sees only the meter + a weather model; the referee sees the
per-inverter breakdown those never touch. Fleet-relative comparison cancels
everything fleet-uniform (weather, soiling, thermal, curtailment) — so it
confirms per-inverter claims and refutes false ones, but is blind to uniform
events BY DESIGN: it can falsify a thermal label, never confirm one.

Run: TRIAGE_SITE=2107 uv run python -m triage.referee
Exits 1 when any classifier label is refuted.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pandas as pd

DIVERGENCE_MARGIN = 0.10  # an inverter this far under the fleet median diverges
FLEET_HEALTHY = 0.5  # only judge days the fleet itself produced meaningfully
TRAIL_DAYS = 30  # per-inverter normalization window
# both PVDAQ naming vintages: inv_01_ac_power_inv_149583 (2107) and
# inverter_01_ac_power_(kw)_inv_150953 (9069)
INV_COL = re.compile(r"(?:inverter|inv)_(\d+)_ac_power")

# per-site electrical streams; vintage order mirrors the meter Streams
ELECTRICAL: dict[str, tuple[str, ...]] = {
    "2107": (
        "2107_electrical_data.csv",
        "2107_electrical_data_2024.csv",
        "2107_electrical_data_2025.csv",
    ),
    "9069": ("9069_electrical_ac.csv",),
}


def load_inverters(files: tuple[str, ...], data_dir: Path, site) -> pd.DataFrame:
    """Per-inverter AC power (kW) on the site grid, columns inv_01..inv_NN."""
    frames = []
    for name in files:
        header = pd.read_csv(data_dir / name, nrows=0).columns
        keep = {
            c: f"inv_{int(m.group(1)):02d}"
            for c in header
            if (m := INV_COL.match(c))
        }
        df = pd.read_csv(  # usecols: the 9069 file is 1.6 GB of mixed channels
            data_dir / name,
            usecols=["measured_on", *keep],
            parse_dates=["measured_on"],
            index_col="measured_on",
        )
        df.index = df.index.tz_localize(
            site.tz, ambiguous="NaT", nonexistent="shift_forward"
        )
        df = df[df.index.notna()]
        frames.append(df.rename(columns=keep))
    out = pd.concat(frames)
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out.resample(site.interval, closed="right", label="right").mean()


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


def cross_check(result: pd.DataFrame, ref: pd.DataFrame) -> pd.DataFrame:
    """Grade classifier claims. outage wants divergence; thermal/weather are
    refuted only when divergent inverters explain most of the day's shortfall
    (a standing dead inverter under a cloudy sky doesn't invalidate the sky
    story); data_gap claims unjudgeability, not plant health, so it is never
    graded; soiling/clipping/unclassified are fleet-uniform or ambiguous —
    uncheckable."""
    rows = []
    for day, row in result.iterrows():
        key = day.normalize()
        known = key in ref.index and pd.notna(ref.at[key, "fleet_median"])
        if not known:
            verdict = "uncheckable"
        else:
            n = ref.at[key, "n_divergent"]
            share = ref.at[key, "div_share"]
            faulty = n >= 1 and pd.notna(share) and share >= 0.5
            collapsed = ref.at[key, "fleet_median"] <= FLEET_HEALTHY
            if row["label"] == "outage":
                # a TOTAL outage has zero divergence by definition — the fleet
                # collapsing with the plant corroborates, it doesn't refute
                verdict = "confirmed" if n >= 1 or collapsed else "refuted"
            elif row["label"] in ("thermal", "weather"):
                verdict = "refuted" if faulty else "confirmed"
            else:
                verdict = "uncheckable"
        rows.append(
            {
                "date": key.date(),
                "label": row["label"],
                "verdict": verdict,
                "divergent": ref.at[key, "divergent"] if known else [],
            }
        )
    return pd.DataFrame(rows).set_index("date")


def main() -> None:
    from triage.build import build
    from triage.classify import classify
    from triage.config import SITES

    key = os.environ.get("TRIAGE_SITE", "2107")
    if key not in ELECTRICAL:
        raise SystemExit(f"no electrical stream registered for site {key}")
    site = SITES[key]
    inv = load_inverters(ELECTRICAL[key], site.source.data_dir, site)
    ref = daily_divergence(inv)
    df, daily = build(site)
    verdicts = cross_check(classify(daily, df, site), ref)
    print(verdicts.to_string())
    counts = verdicts["verdict"].value_counts()
    print(f"\n{counts.to_string()}")
    if counts.get("refuted", 0):
        raise SystemExit(1)  # a refuted label fails the run loudly


if __name__ == "__main__":
    main()
