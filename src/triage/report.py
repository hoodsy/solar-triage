from pathlib import Path

import pandas as pd

from triage.config import SITE
from triage.plot import plot_day, plot_energy, plot_pi

REPORT_HEAD = """<!doctype html>
<html><head>
<meta charset="utf-8">
<title>Solar triage report</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Nunito+Sans:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  body { font-family: "Nunito Sans", sans-serif; background: #F5F6F7;
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
</head><body><div class="wrap">"""


def write_report(
    result: pd.DataFrame,
    daily: pd.DataFrame,
    df: pd.DataFrame,
    path: str = "reports/report.html",
) -> None:
    """One HTML page: season energy + PI overview, then per-flagged-day evidence charts."""

    def card(inner: str) -> str:
        return f'<div class="card">{inner}</div>'

    table = result.copy()
    table.index = table.index.date  # dates, not full timestamps, in the summary

    parts = [
        REPORT_HEAD,
        f"<h1>Solar triage report — {SITE.name}</h1>",
        "<h2>Season energy</h2>",
        '<p class="desc">Daily measured energy (blue) against the irradiance-driven '
        "expectation (gray); gray showing above blue is energy the site failed to produce.</p>",
        card(plot_energy(daily).to_html(full_html=False, include_plotlyjs=True)),
        "<h2>Performance index &amp; flags</h2>",
        '<p class="desc">Daily PI (actual / expected) against its rolling baseline; '
        "red markers are flagged days, judged against the dotted threshold.</p>",
        card(plot_pi(daily).to_html(full_html=False, include_plotlyjs=False)),
        "<h2>Flagged days</h2>",
        f'<p class="desc">{len(result)} flagged days, each given one label and its '
        "evidence (precedence: outage &gt; clipping &gt; soiling &gt; unclassified).</p>",
        card(table.to_html(border=0)),
    ]
    for day, row in result.iterrows():
        fig = plot_day(df, day.strftime("%Y-%m-%d"))
        parts.append(
            card(
                f"<h3>{day.date()} — {row['label']} (PI {row['pi']:.2f})</h3>"
                f'<p class="evidence">{row["evidence"]}</p>'
                + fig.to_html(full_html=False, include_plotlyjs=False)
            )
        )
    parts.append("</div></body></html>")
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(parts))
