from types import SimpleNamespace

import pandas as pd

from triage.build import build_daily, build_dataset


class StubSource:
    def __init__(self, df):
        self.df = df

    def load(self, site):
        return self.df


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


def test_build_dataset_falls_back_to_clearsky_without_poa():
    idx = pd.date_range("2024-06-01", periods=96, freq="15min", tz="Pacific/Auckland")
    site = SimpleNamespace(
        source=StubSource(pd.DataFrame({"ac_power_kw": 10.0}, index=idx)),
        lat=-36.9,
        lon=174.8,
        tilt=25.0,
        azimuth=0.0,  # north-facing in the southern hemisphere
        tz="Pacific/Auckland",
        dc_capacity_kw=50.0,
        derate=0.8,
    )
    exp = build_dataset(site)["expected_kw"]
    assert (exp.fillna(0) >= 0).all()
    assert exp.between_time("11:00", "14:00").max() > 10  # real winter midday power
