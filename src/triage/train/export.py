"""Per-day training export: one CSV row per day of the report window.

The training set a future classifier learns from. Every day appears —
healthy days carry the negative class — with the day's feature vector
(the shape measurements the rules read; see features.py), the rule
label, the post-referee final label, and a provenance column separating
fleet-graded gold (confirmed/refuted/attributed) from rule-only weak
labels. Schema is identical across sites (rain_mm/verdict/features empty
or NaN where a site lacks them) so multi-site concatenation needs no
alignment.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from triage.classify import day_slice
from triage.train.features import FEATURE_COLUMNS, day_features

if TYPE_CHECKING:
    from triage.config import SiteConfig

HEALTHY = "healthy"  # export-only vocabulary: unflagged day, not a Fault
GOLD_VERDICTS = ("confirmed", "refuted", "attributed")

COLUMNS = [
    "site", "actual_kwh", "expected_kwh", "pi", "pi_baseline", "coverage",
    "rain_mm", "snow_cm", "flagged", *FEATURE_COLUMNS, "rule_label",
    "final_label", "final_label_2", "verdict", "provenance", "evidence",
]


def training_frame(
    daily: pd.DataFrame,
    result: pd.DataFrame,
    final: pd.DataFrame,
    key: str,
    df: pd.DataFrame | None = None,
    site: SiteConfig | None = None,
) -> pd.DataFrame:
    """Assemble the per-day frame from the three pipeline stages: flagged
    dailies, classifier output, and referee-resolved final labels — plus,
    when the interval frame and site are given, the per-day feature
    vector every row (healthy days included: the model must see what
    normal shapes look like too)."""
    out = daily.copy()
    out.insert(0, "site", key)
    for c in ("rain_mm", "snow_cm"):
        if c not in out.columns:
            out[c] = float("nan")
    if df is not None and site is not None:
        feats = pd.DataFrame(
            [day_features(day, day_slice(df, day), daily, site) for day in out.index],
            index=out.index,
        )
        out = out.join(feats)
    else:  # feature-less callers still get the full schema, as NaN
        for c in FEATURE_COLUMNS:
            out[c] = float("nan")
    # str() per value: StrEnum defeats astype(str) (see project gotchas)
    out["rule_label"] = HEALTHY
    out.loc[result.index, "rule_label"] = result["label"].map(str)
    out["final_label"] = HEALTHY
    out.loc[final.index, "final_label"] = final["label"].map(str)
    # secondary label: referee-split days (e.g. weather + a divergent-inverter
    # loss riding under it) carry the minor component here
    out["final_label_2"] = ""
    if "label_2" in final.columns:
        has2 = final["label_2"].notna()
        out.loc[final.index[has2], "final_label_2"] = (
            final.loc[has2, "label_2"].map(str)
        )
    out["verdict"] = ""
    if "verdict" in final.columns:
        out.loc[final.index, "verdict"] = final["verdict"]
    # gold iff the fleet actually graded the day; "uncheckable" rests on
    # rule evidence alone and must weigh like any other rule label
    out["provenance"] = out["verdict"].isin(GOLD_VERDICTS).map(
        {True: "referee", False: "rule"}
    )
    out["evidence"] = ""
    out.loc[final.index, "evidence"] = final["evidence"]
    out.index = pd.Index(out.index.date, name="date")
    return out[COLUMNS]


def export_training(
    daily: pd.DataFrame,
    result: pd.DataFrame,
    final: pd.DataFrame,
    key: str,
    df: pd.DataFrame | None = None,
    site: SiteConfig | None = None,
    out_dir: Path = Path("reports"),
) -> Path:
    """Write reports/<key>/<key>-<run timestamp>.csv; returns the path."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = out_dir / key / f"{key}-{stamp}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    training_frame(daily, result, final, key, df, site).to_csv(path)
    return path
