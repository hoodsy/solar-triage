from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

if TYPE_CHECKING:
    from triage.config import SiteConfig


def plot_energy(daily: pd.DataFrame) -> go.Figure:
    long = daily.reset_index().melt(
        id_vars="measured_on", value_vars=["expected_kwh", "actual_kwh"]
    )
    fig = px.line(
        long,
        x="measured_on",
        y="value",
        color="variable",
        color_discrete_sequence=[
            "#9498A0",
            "#4269D0",
        ],  # expected = gray reference, actual = blue
        template="simple_white",
        labels={"measured_on": "", "value": "kWh/day", "variable": ""},
    )
    fig.update_traces(fill="tozeroy", line_width=2)
    for trace, rgba in zip(
        fig.data, ["rgba(148,152,160,0.30)", "rgba(66,105,208,0.35)"]
    ):
        trace.fillcolor = rgba
    fig.update_layout(font=dict(family="Nunito Sans, sans-serif"))
    return fig


def plot_pi(daily: pd.DataFrame, site: SiteConfig) -> go.Figure:
    flagged = daily[daily["flagged"]]
    fig = go.Figure()
    fig.add_scatter(
        x=daily.index,
        y=site.flag_threshold * daily["pi_baseline"],
        name="flag threshold",
        line=dict(color="#C3C7CF", width=1, dash="dot"),
    )
    fig.add_scatter(
        x=daily.index,
        y=daily["pi_baseline"],
        name=f"{site.window}-day baseline",
        line=dict(color="#9498A0", width=2, dash="dash"),
    )
    fig.add_scatter(
        x=daily.index, y=daily["pi"], name="PI", line=dict(color="#4269D0", width=2)
    )
    fig.add_scatter(
        x=flagged.index,
        y=flagged["pi"],
        mode="markers",
        name="flagged",
        marker=dict(color="#B3324B", size=9),
    )
    fig.update_layout(
        template="simple_white",
        yaxis_title="PI",
        font=dict(family="Nunito Sans, sans-serif"),
        legend=dict(orientation="h", y=1.02, yanchor="bottom"),
    )
    return fig


def plot_day(df: pd.DataFrame, day: str, site: SiteConfig, title: str = "") -> go.Figure:
    d = df.loc[day]
    fig = go.Figure()
    fig.add_scatter(
        x=d.index,
        y=d["expected_kw"],
        name="expected",
        line=dict(color="#9498A0", width=2, dash="dash"),
    )
    fig.add_scatter(
        x=d.index,
        y=d["ac_power_kw"],
        name="actual",
        line=dict(color="#4269D0", width=2),
        fill="tozeroy",
        fillcolor="rgba(66,105,208,0.35)",
    )
    fig.add_hline(
        y=site.ac_capacity_kw,
        line=dict(color="#C3C7CF", width=1, dash="dot"),
        annotation_text="AC ceiling",
        annotation_font_color="#9498A0",
    )
    fig.update_layout(
        template="simple_white",
        title=title,
        yaxis_title="kW",
        height=350,
        font=dict(family="Nunito Sans, sans-serif"),
        legend=dict(orientation="h", y=1.02, yanchor="bottom"),
    )
    return fig
