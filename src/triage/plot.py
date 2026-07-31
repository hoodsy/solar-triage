from __future__ import annotations

from typing import TYPE_CHECKING

import plotly.express as px
import plotly.graph_objects as go

if TYPE_CHECKING:
    import pandas as pd

    from triage.config import SiteConfig

# one palette for every figure: blue = measured, gray = model/reference,
# light gray = thresholds/ceilings, red = flags
BLUE, BLUE_FILL = "#4269D0", "rgba(66,105,208,0.35)"
GRAY, GRAY_FILL = "#9498A0", "rgba(148,152,160,0.30)"
GRID = "#C3C7CF"
RED = "#B3324B"
FONT = "Nunito Sans"


def _layout(fig: go.Figure, **kw) -> go.Figure:
    fig.update_layout(
        template="simple_white",
        font=dict(family=f"{FONT}, sans-serif"),
        legend=dict(orientation="h", y=1.02, yanchor="bottom"),
        **kw,
    )
    return fig


def plot_energy(daily: pd.DataFrame) -> go.Figure:
    long = daily.reset_index().melt(
        id_vars="measured_on", value_vars=["expected_kwh", "actual_kwh"]
    )
    fig = px.line(
        long,
        x="measured_on",
        y="value",
        color="variable",
        color_discrete_sequence=[GRAY, BLUE],  # expected = reference, actual = blue
        labels={"measured_on": "", "value": "kWh/day", "variable": ""},
    )
    fig.update_traces(fill="tozeroy", line_width=2)
    for trace, rgba in zip(fig.data, [GRAY_FILL, BLUE_FILL]):
        trace.fillcolor = rgba
    return _layout(fig)


def plot_pi(daily: pd.DataFrame, site: SiteConfig) -> go.Figure:
    flagged = daily[daily["flagged"]]
    fig = go.Figure()
    fig.add_scatter(
        x=daily.index,
        y=site.flag_threshold * daily["pi_baseline"],
        name="flag threshold",
        line=dict(color=GRID, width=1, dash="dot"),
    )
    fig.add_scatter(
        x=daily.index,
        y=daily["pi_baseline"],
        name=f"{site.window}-day baseline",
        line=dict(color=GRAY, width=2, dash="dash"),
    )
    fig.add_scatter(
        x=daily.index, y=daily["pi"], name="PI", line=dict(color=BLUE, width=2)
    )
    fig.add_scatter(
        x=flagged.index,
        y=flagged["pi"],
        mode="markers",
        name="flagged",
        marker=dict(color=RED, size=9),
    )
    return _layout(fig, yaxis_title="PI")


def plot_day(intraday: pd.DataFrame, site: SiteConfig) -> go.Figure:
    fig = go.Figure()
    fig.add_scatter(
        x=intraday.index,
        y=intraday["expected_kw"] if "expected_kw" in intraday.columns else [],
        name="expected",
        line=dict(color=GRAY, width=2, dash="dash"),
    )
    fig.add_scatter(
        x=intraday.index,
        y=intraday["ac_power_kw"] if "ac_power_kw" in intraday.columns else [],
        name="actual",
        line=dict(color=BLUE, width=2),
        fill="tozeroy",
        fillcolor=BLUE_FILL,
    )
    fig.add_hline(
        y=site.ac_capacity_kw,
        line=dict(color=GRID, width=1, dash="dot"),
        annotation_text="AC ceiling",
        annotation_font_color=GRAY,
    )
    return _layout(fig, yaxis_title="kW", height=350)
