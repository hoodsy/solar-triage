from types import SimpleNamespace

import pandas as pd

from triage.ingest import build_daily


def make_frame(interval, periods, kw=100.0):
    idx = pd.date_range("2024-06-01", periods=periods, freq=interval, tz="US/Pacific")
    return pd.DataFrame({"ac_power_kw": kw, "expected_kw": kw}, index=idx)


def test_build_daily_hourly():
    daily = build_daily(make_frame("1h", 24), SimpleNamespace(interval="1h"))
    assert daily["actual_kwh"].iloc[0] == 100.0 * 24  # 24 intervals x 1h each
    assert daily["coverage"].iloc[0] == 1.0


def test_build_daily_15min_regression():
    daily = build_daily(make_frame("15min", 96), SimpleNamespace(interval="15min"))
    assert daily["actual_kwh"].iloc[0] == 100.0 * 24  # 96 intervals x 0.25h
    assert daily["coverage"].iloc[0] == 1.0
