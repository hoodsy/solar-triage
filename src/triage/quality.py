"""Data-quality gate: mask untrustworthy intervals before they reach PI.

pvanalytics primitives (per-interval booleans) applied to each measured
stream; failing intervals become NaN, so bad data flows into the existing
coverage -> data_gap machinery instead of masquerading as performance.

Zeros are never masked as stale: a flatline at zero in daylight is outage
evidence (the dead-run rule's whole signal), not sensor stickiness. The
same logic exempts the AC ceiling: a flatline at >=90% of ac_capacity is
clipping physics (2107: 70 of 81 "stale" intervals were midday values at
695-707 kW), so staleness only applies between the floor and the ceiling.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pvanalytics.quality import gaps, weather

POA_MIN_WM2 = -10.0  # thermopile night offsets sit a few W/m2 below zero
POA_CSI_MAX = 1.5  # broken-cloud enhancement is real to ~1.3x clear sky


def clean(
    df: pd.DataFrame, site, clearsky_poa_wm2: pd.Series | None = None
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Mask bad intervals in the measured streams; report counts per check.

    Runs on the adapter's output only — modeled columns (Open-Meteo met,
    expected power) join downstream and are not sensor data to validate.
    """
    df = df.copy()
    masked: dict[str, int] = {}

    def mask(column: str, bad: pd.Series, check: str) -> None:
        n = int(bad.fillna(False).sum())
        if n:
            df.loc[bad.fillna(False), column] = np.nan
        masked[check] = n

    ac = df["ac_power_kw"]
    judgeable = (ac != 0) & (ac < 0.9 * site.ac_capacity_kw)
    mask("ac_power_kw", gaps.stale_values_diff(ac.dropna()).reindex(df.index) & judgeable, "meter stale")
    mask("ac_power_kw", gaps.interpolation_diff(ac.dropna()).reindex(df.index) & judgeable, "meter interpolated")

    if "poa_wm2" in df.columns:
        poa = df["poa_wm2"]
        mask("poa_wm2", poa < POA_MIN_WM2, "poa negative")
        mask("poa_wm2", gaps.stale_values_diff(poa.dropna()).reindex(df.index) & (poa > 0), "poa stale")
        if clearsky_poa_wm2 is not None:
            from pvanalytics.quality import irradiance

            ok = irradiance.clearsky_limits(poa, clearsky_poa_wm2, csi_max=POA_CSI_MAX)
            mask(
                "poa_wm2",
                # only judge the ceiling when the model is meaningfully bright:
                # at low sun the clearsky model's horizon/turbidity error, not
                # the sensor, produces csi > 1.5 (2107: 90% of hits were 7-9h
                # and 15-19h before this floor)
                ~ok & poa.notna() & (clearsky_poa_wm2 > 200),
                "poa above clear ceiling",
            )

    if "temp_c" in df.columns:
        t = df["temp_c"]
        mask("temp_c", ~weather.temperature_limits(t) & t.notna(), "temp out of range")

    return df, {k: v for k, v in masked.items() if v}
