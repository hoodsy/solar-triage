"""Data-quality gate: mask untrustworthy intervals before they reach PI.

pvanalytics primitives (per-interval booleans) applied to each measured
stream; failing intervals become NaN, so bad data flows into the existing
coverage -> data_gap machinery instead of masquerading as performance.

Zeros are never masked as stale: a flatline at zero in daylight is outage
evidence (the dead-run rule's whole signal), not sensor stickiness.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pvanalytics.quality import gaps, weather

POA_MIN_WM2 = -10.0  # thermopile night offsets sit a few W/m2 below zero
POA_CSI_MAX = 1.5  # broken-cloud enhancement is real to ~1.3x clear sky


def clean(
    df: pd.DataFrame, clearsky_poa_wm2: pd.Series | None = None
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
    mask("ac_power_kw", gaps.stale_values_diff(ac.dropna()).reindex(df.index) & (ac != 0), "meter stale")
    mask("ac_power_kw", gaps.interpolation_diff(ac.dropna()).reindex(df.index) & (ac != 0), "meter interpolated")

    if "poa_wm2" in df.columns:
        poa = df["poa_wm2"]
        mask("poa_wm2", poa < POA_MIN_WM2, "poa negative")
        mask("poa_wm2", gaps.stale_values_diff(poa.dropna()).reindex(df.index) & (poa > 0), "poa stale")
        if clearsky_poa_wm2 is not None:
            from pvanalytics.quality import irradiance

            ok = irradiance.clearsky_limits(poa, clearsky_poa_wm2, csi_max=POA_CSI_MAX)
            mask(
                "poa_wm2",
                ~ok & poa.notna() & (clearsky_poa_wm2 > 50),
                "poa above clear ceiling",
            )

    if "temp_c" in df.columns:
        t = df["temp_c"]
        mask("temp_c", ~weather.temperature_limits(t) & t.notna(), "temp out of range")

    return df, {k: v for k, v in masked.items() if v}
