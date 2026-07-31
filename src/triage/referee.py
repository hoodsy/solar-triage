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
INV_COL = re.compile(r"(inv_\d+)_ac_power_inv_\d+")

# 2107 vintages, newest wins on overlap — mirrors the meter Stream in config
ELECTRICAL_FILES = (
    "2107_electrical_data.csv",
    "2107_electrical_data_2024.csv",
    "2107_electrical_data_2025.csv",
)


def load_inverters(files: tuple[str, ...], data_dir: Path, site) -> pd.DataFrame:
    """Per-inverter AC power (kW) on the site grid, columns inv_01..inv_NN."""
    frames = []
    for name in files:
        df = pd.read_csv(
            data_dir / name, parse_dates=["measured_on"], index_col="measured_on"
        )
        df.index = df.index.tz_localize(
            site.tz, ambiguous="NaT", nonexistent="shift_forward"
        )
        df = df[df.index.notna()]
        keep = {c: m.group(1) for c in df.columns if (m := INV_COL.match(c))}
        frames.append(df[list(keep)].rename(columns=keep))
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
    return pd.DataFrame(
        {
            "n_divergent": divergent.sum(axis=1).astype(int),
            "divergent": divergent.apply(lambda r: list(r.index[r]), axis=1),
            "fleet_median": fleet,
        }
    )


def cross_check(result: pd.DataFrame, ref: pd.DataFrame) -> pd.DataFrame:
    """Grade classifier claims. outage wants divergence; thermal/weather/
    data_gap want none; soiling/clipping/unclassified are fleet-uniform or
    ambiguous — uncheckable."""
    rows = []
    for day, row in result.iterrows():
        key = day.normalize()
        known = key in ref.index and pd.notna(ref.at[key, "fleet_median"])
        if not known:
            verdict = "uncheckable"
        else:
            n = ref.at[key, "n_divergent"]
            if row["label"] == "outage":
                verdict = "confirmed" if n >= 1 else "refuted"
            elif row["label"] in ("thermal", "weather", "data_gap"):
                verdict = "confirmed" if n == 0 else "refuted"
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

    site = SITES[os.environ.get("TRIAGE_SITE", "2107")]
    inv = load_inverters(ELECTRICAL_FILES, site.source.data_dir, site)
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
