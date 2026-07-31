from types import SimpleNamespace

import numpy as np
import pandas as pd

from triage.classify import Fault, chop_mad, classify_day, day_csr, detect_soiling


def make_daily(pi_values) -> pd.DataFrame:
    idx = pd.date_range(
        "2024-01-01", periods=len(pi_values), freq="1D", tz="US/Pacific"
    )
    return pd.DataFrame({"pi": list(pi_values), "pi_baseline": 1.0}, index=idx)


# detect_soiling reads neither intraday data nor site config, so None stands
# in for both — the uniform detector signature is the only reason they exist.


def test_fires_on_gradual_decline():
    daily = make_daily(1.0 - 0.004 * np.arange(16))  # smooth -0.4%/day slide
    assert detect_soiling(daily.index[-1], None, daily, None) is not None


def test_rejects_single_step():
    daily = make_daily([1.0] * 12 + [0.85] * 4)  # flat, then one -15% step
    assert detect_soiling(daily.index[-1], None, daily, None) is None


def test_rejects_double_step():
    daily = make_daily([1.0] * 6 + [0.93] * 5 + [0.86] * 5)  # two -7% steps
    assert detect_soiling(daily.index[-1], None, daily, None) is None


def test_low_coverage_day_labeled_data_gap():
    daily = make_daily([1.0] * 5)
    daily["coverage"] = [1.0, 1.0, 0.5, 1.0, 1.0]
    site = SimpleNamespace(coverage_min=0.8)
    label, evidence = classify_day(daily.index[2], None, daily, site)
    assert label == Fault.DATA_GAP
    assert "50%" in evidence


def make_intraday(actual, expected, clearsky=None, temp=None, tz="UTC"):
    """One synthetic day on a 15-min grid from hourly values (07:00 onward)."""
    hours = pd.date_range("2025-01-15 07:00", periods=len(actual), freq="1h", tz=tz)
    idx = pd.date_range(hours[0], hours[-1] + pd.Timedelta("45min"), freq="15min")
    df = pd.DataFrame(index=idx)
    df["ac_power_kw"] = np.repeat(list(actual), 4)
    df["expected_kw"] = np.repeat(list(expected), 4)
    if clearsky is not None:
        df["clearsky_kw"] = np.repeat(list(clearsky), 4)
    if temp is not None:
        df["temp_c"] = np.repeat(list(temp), 4).astype(float)
    return df


CHOP_SITE = SimpleNamespace(dc_capacity_kw=2.0)


def test_csr_measures_sun_vs_clear_ceiling():
    day = make_intraday([0.5] * 8, [1.0] * 8, clearsky=[1.0] * 8)
    assert abs(day_csr(day) - 0.5) < 0.01


def test_csr_nan_without_clearsky_column():
    day = make_intraday([0.5] * 8, [1.0] * 8)
    assert pd.isna(day_csr(day))


def test_chop_high_on_broken_sky():
    # ratio alternates 0.9/0.4 hour to hour — sawtooth
    actual = [0.9, 0.4, 0.9, 0.4, 0.9, 0.4, 0.9, 0.4]
    day = make_intraday(actual, [1.0] * 8)
    assert chop_mad(day, CHOP_SITE) > 0.10


def test_chop_low_on_smooth_derate():
    # uniform 60% output: a fault scales smoothly
    day = make_intraday([0.6] * 8, [1.0] * 8)
    assert chop_mad(day, CHOP_SITE) < 0.10
