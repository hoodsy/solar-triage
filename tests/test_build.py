from types import SimpleNamespace

import pandas as pd

from triage.build import add_flags, build_daily, build_dataset


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
        weather=None,  # no reanalysis source -> clear-sky tier
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


def make_flag_daily(pi_values):
    idx = pd.date_range("2025-01-01", periods=len(pi_values), freq="1D", tz="UTC")
    return pd.DataFrame(
        {"pi": list(pi_values), "coverage": 1.0,
         "actual_kwh": 1.0, "expected_kwh": 1.0},
        index=idx,
    )


FLAG_SITE = SimpleNamespace(coverage_min=0.8, flag_threshold=0.92, window=30)


def test_long_outage_stays_flagged():
    # 60 healthy days then 45 dead days: every dead day must flag
    daily = add_flags(make_flag_daily([1.0] * 60 + [0.0] * 45), FLAG_SITE)
    assert daily["flagged"].iloc[60:].all()


def test_baseline_freezes_when_window_runs_dry():
    daily = add_flags(make_flag_daily([1.0] * 60 + [0.0] * 45), FLAG_SITE)
    # once every trailing day is flagged, baseline holds last good value
    assert daily["pi_baseline"].iloc[-1] > 0.9
    assert daily["pi_baseline"].iloc[60:].notna().all()


def test_sparse_dips_unchanged_by_convergence():
    # isolated dips converge to the same answer the two-pass loop found
    pi = [1.0] * 40 + [0.7] + [1.0] * 20 + [0.65] + [1.0] * 20
    daily = add_flags(make_flag_daily(pi), FLAG_SITE)
    assert daily["flagged"].sum() == 2
    assert daily["flagged"].iloc[40] and daily["flagged"].iloc[61]


def test_low_coverage_day_is_flagged():
    daily = make_flag_daily([1.0] * 40)
    daily.iloc[35, daily.columns.get_loc("coverage")] = 0.5
    out = add_flags(daily, FLAG_SITE)
    assert out["flagged"].iloc[35]
    assert pd.isna(out["pi"].iloc[35])  # still excluded from baseline math
