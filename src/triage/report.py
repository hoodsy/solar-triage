from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from triage.classify import day_slice, precedence
from triage.plot import FONT, plot_day, plot_energy, plot_pi

if TYPE_CHECKING:
    from triage.config import SiteConfig

REPORT_HEAD = """<!doctype html>
<html><head>
<meta charset="utf-8">
<title>Solar triage report</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=$FONT:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  body { font-family: "$FONT", sans-serif; background: #F5F6F7;
         color: #1F2328; margin: 0; padding: 32px 16px; }
  .wrap { max-width: 960px; margin: 0 auto; }
  h1 { font-size: 1.6rem; }
  h2 { font-size: 1.2rem; margin: 32px 0 4px; }
  p.desc { color: #57606A; margin: 4px 0 12px; }
  .card { background: #fff; border: 1px solid #E3E5E8; border-radius: 12px;
          padding: 20px; margin: 16px 0; overflow-x: auto; }
  .card h3 { margin: 0 0 4px; font-size: 1.05rem; }
  .card p.evidence { color: #57606A; margin: 0 0 8px; font-size: 0.9rem; }
  table.dataframe { border-collapse: collapse; width: 100%; font-size: 0.85rem; }
  table.dataframe th, table.dataframe td { padding: 6px 10px; text-align: left;
          border-bottom: 1px solid #EEF0F2; }
  table.dataframe thead th { border-bottom: 2px solid #E3E5E8; }
</style>
</head><body><div class="wrap">""".replace("$FONT", FONT)


def report(
    final: pd.DataFrame,
    ev: pd.DataFrame,
    daily: pd.DataFrame,
    df: pd.DataFrame,
    site: SiteConfig,
    *,
    masked: dict[str, int],
    degradation: str,
    soiling: str,
    path: str = "reports/report.html",
) -> None:
    """One HTML page for the whole pipeline run: energy + PI overview, data
    quality, events, final labels (+ referee verdicts where sub-metered),
    slow trends, then per-flagged-day evidence charts."""

    def card(inner: str) -> str:
        return f'<div class="card">{inner}</div>'

    graded = "verdict" in final.columns
    label_counts = (
        pd.Series({str(k): v for k, v in final["label"].value_counts().items()})
        .rename_axis("label")
        .to_frame("days")
    )
    table = final.copy()
    table.index = table.index.date  # dates, not full timestamps, in the summary

    parts = [
        REPORT_HEAD,
        f"<h1>Solar triage report — {site.name}</h1>",
        "<h2>Season energy</h2>",
        '<p class="desc">Daily measured energy (blue) against the irradiance-driven '
        "expectation (gray); gray showing above blue is energy the site failed to produce.</p>",
        card(plot_energy(daily).to_html(full_html=False, include_plotlyjs=True)),
        "<h2>Performance index &amp; flags</h2>",
        '<p class="desc">Daily PI (actual / expected) against its rolling baseline; '
        "red markers are flagged days, judged against the dotted threshold.</p>",
        card(plot_pi(daily, site).to_html(full_html=False, include_plotlyjs=False)),
        "<h2>Data quality</h2>",
        '<p class="desc">Sensor readings that failed plausibility checks are masked '
        "to missing before any performance math — bad instrumentation surfaces as "
        "data_gap days, not fake verdicts.</p>",
        card(
            pd.Series(masked, name="intervals masked")
            .rename_axis("check")
            .to_frame()
            .to_html(border=0)
            if masked
            else "<p>no intervals masked</p>"
        ),
        "<h2>Events</h2>",
        '<p class="desc">Consecutive same-label days merged; data-gap days bridge '
        "an event rather than splitting it. Deficit is energy the site failed to "
        "produce over the event.</p>",
        card(ev.to_html(border=0, index=False)),
        "<h2>Final labels</h2>",
        '<p class="desc">'
        + (
            "Classifier labels refined by per-inverter attribution — the referee "
            "grades meter-level claims against the fleet and resolves unclassified "
            "days it can explain."
            if graded
            else "Classifier only — this site has no sub-metering, so labels rest "
            "on meter-level evidence alone."
        )
        + f' Rule precedence: {" &gt; ".join(precedence())}.</p>',
        card(label_counts.to_html(border=0)),
    ]
    if graded:
        refuted = table[table["verdict"] == "refuted"]
        parts += [
            "<h2>Verdicts on classifier claims</h2>",
            '<p class="desc">Per-inverter grading of each meter-level claim: '
            "confirmed (fleet corroborates), refuted (fleet contradicts — a "
            "classifier limitation worth reading), attributed (referee resolved "
            "an unclassified day), uncheckable (fleet-uniform or no data).</p>",
            card(
                final["verdict"]
                .value_counts()
                .rename_axis("verdict")
                .to_frame("days")
                .to_html(border=0)
                + (
                    "<p class='evidence'>refuted days:</p>"
                    + refuted[["label", "evidence"]].to_html(border=0)
                    if len(refuted)
                    else ""
                )
            ),
        ]
    parts += [
        "<h2>Slow trends</h2>",
        '<p class="desc">Standing conditions the rolling baseline is blind to, '
        "measured over the full data span (RdTools).</p>",
        card(f"<p>degradation: {degradation}</p><p>soiling: {soiling}</p>"),
    ]
    for day, row in final.iterrows():
        pi_txt = f"PI {row['pi']:.2f}" if pd.notna(row["pi"]) else "no PI"
        verdict_txt = (
            f" · referee: {row['verdict']}" if graded and pd.notna(row["verdict"]) else ""
        )
        label_txt = str(row["label"])
        if "label_2" in final.columns and pd.notna(row["label_2"]):
            label_txt += f" + {row['label_2']}"
        parts.append(
            card(
                f"<h3>{day.date()} — {label_txt} ({pi_txt}){verdict_txt}</h3>"
                f'<p class="evidence">{row["evidence"]}</p>'
                + plot_day(day_slice(df, day), site).to_html(
                    full_html=False, include_plotlyjs=False
                )
            )
        )
    parts.append("</div></body></html>")
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(parts))
