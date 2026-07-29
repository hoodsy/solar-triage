from pathlib import Path
import pandas as pd
import json
import plotly.express as px
import plotly.graph_objects as go

DATA_DIR = Path("data/2107/data")
DC_CAPACITY_KW = 893.0
DERATE = 0.8
COVERAGE_MIN = 0.8
FLAG_THRESHOLD = 0.92  # flag 8% and more underperformance
WINDOW = 30  # days


def build_meter() -> pd.DataFrame:
    FILES = [
        "2107_meter_15m_data.csv",  # 2017-01 → 2023-11
        "2107_meter_15m_data_2024.csv",  # 2024-01 → 2024-11
        "2107_meter_15m_data_2025.csv",  # 2024-02 → 2025-12
    ]
    meter = pd.concat(
        pd.read_csv(DATA_DIR / f, parse_dates=["measured_on"], index_col="measured_on")
        for f in FILES
    )
    meter = meter[~meter.index.duplicated(keep="last")].sort_index()
    meter.index = meter.index.tz_localize(
        "US/Pacific",
        ambiguous="NaT",  # can't resolve the once-recorded fall-back hour
        nonexistent="shift_forward",  # shouldn't occur in this data; don't crash if it does
    )
    meter = meter[meter.index.notna()]  # drop the NaT'd ambiguous rows
    return meter


def build_irradiance() -> pd.DataFrame:
    frames = []
    FILES = [
        "2107_irradiance_data.csv",
        "2107_irradiance_data_2024.csv",
    ]
    for f in FILES:
        df = pd.read_csv(
            DATA_DIR / f, parse_dates=["measured_on"], index_col="measured_on"
        )
        df.index = df.index.tz_localize(
            "US/Pacific", ambiguous="NaT", nonexistent="shift_forward"
        )
        df = df[df.index.notna()]
        frames.append(df)

    UTC_FILE = "2107_irradiance_15m_data_2025.csv"
    utc = pd.read_csv(
        DATA_DIR / UTC_FILE,
        parse_dates=["utc_measured_on"],
        index_col="utc_measured_on",
    )
    utc.index = utc.index.tz_localize("UTC").tz_convert("US/Pacific")
    utc.index.name = "measured_on"
    frames.append(utc)

    irradiance = pd.concat(frames)
    irradiance = irradiance[~irradiance.index.duplicated(keep="first")].sort_index()
    return irradiance


def build_dataset() -> pd.DataFrame:
    meter = build_meter().rename(columns=lambda c: "ac_power_kw")
    poa = build_irradiance().rename(columns=lambda c: "poa_wm2")
    poa_15 = poa.resample("15min", closed="right", label="right").mean()
    return meter.join(poa_15, how="outer")


def build_daily(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["expected_kw"] = DC_CAPACITY_KW * (df["poa_wm2"] / 1000.0) * DERATE

    daily = pd.DataFrame(
        {
            "actual_kwh": df["ac_power_kw"].resample("1D").sum(min_count=1) * 0.25,
            "expected_kwh": df["expected_kw"].resample("1D").sum(min_count=1) * 0.25,
            "coverage": df["ac_power_kw"].resample("1D").count() / 96,
        }
    )
    daily["pi"] = daily["actual_kwh"] / daily["expected_kwh"].where(
        daily["expected_kwh"] > 0
    )
    return daily


def add_flags(daily: pd.DataFrame) -> pd.DataFrame:
    daily = daily.copy()
    daily["pi"] = daily["pi"].where(
        daily["coverage"] >= COVERAGE_MIN
    )  # exclude days with 20% or less data
    # ignore flagged days in the pi_baseline
    flagged = pd.Series(False, index=daily.index)
    for _ in range(2):
        baseline = (
            daily["pi"]
            .where(~flagged)
            .shift(1)
            .rolling(WINDOW, min_periods=WINDOW // 2)
            .median()
        )
        flagged = daily["pi"] < FLAG_THRESHOLD * baseline

    daily["pi_baseline"] = baseline
    daily["flagged"] = flagged
    return daily


def plot_energy(df: pd.DataFrame):
    fig = px.line(
        df,
        x="measured_on",
        y="value",
        color="variable",
        color_discrete_sequence=[
            "#9498A0",
            "#4269D0",
        ],  # expected = gray reference, actual = blue
        template="simple_white",
        title="Daily energy: actual vs expected — 2024",
        labels={"measured_on": "", "value": "kWh/day", "variable": ""},
    )
    fig.update_traces(line_width=2)
    fig.update_traces(fill="tozeroy", line_width=2)
    for trace, rgba in zip(
        fig.data, ["rgba(148,152,160,0.30)", "rgba(66,105,208,0.35)"]
    ):
        trace.fillcolor = rgba
    fig.show()


def plot_pi(daily: pd.DataFrame) -> go.Figure:
    flagged = daily[daily["flagged"]]
    fig = go.Figure()
    fig.add_scatter(
        x=daily.index,
        y=FLAG_THRESHOLD * daily["pi_baseline"],
        name="flag threshold",
        line=dict(color="#C3C7CF", width=1, dash="dot"),
    )
    fig.add_scatter(
        x=daily.index,
        y=daily["pi_baseline"],
        name=f"{WINDOW}-day baseline",
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
        title="Daily performance index",
        yaxis_title="PI",
        legend=dict(orientation="h", y=1.02, yanchor="bottom"),
    )
    fig.show()
    return fig


# Metadata units reference
# meta = json.loads(Path("data/2107/metadata/2107_system_metadata.json").read_text())
# units = {col: (m["common_name"], m["units"]) for col, m in meta["Metrics"].items()}


def main():
    df = build_dataset()
    # daily = build_daily(df).loc["2022-01-01":"2025-11-30"]
    daily = build_daily(df).loc["2024-01-01":"2024-11-30"]
    daily = add_flags(daily)

    long = daily.reset_index().melt(
        id_vars="measured_on", value_vars=["expected_kwh", "actual_kwh"]
    )
    plot_energy(long)
    plot_pi(daily)


if __name__ == "__main__":
    main()
