import numpy as np
import pandas as pd

from triage.trend import degradation


def test_yoy_detects_synthetic_decline():
    idx = pd.date_range("2020-01-01", periods=3 * 365, freq="1D", tz="UTC")
    rng = np.random.default_rng(7)
    pi = pd.Series(
        1.0 - 0.01 * np.arange(len(idx)) / 365 + rng.normal(0, 0.02, len(idx)),
        index=idx,
    )  # -1%/yr with realistic noise
    out = degradation(pi)
    assert "%/yr" in out
    assert out.startswith("-0.") or out.startswith("-1.")


def test_yoy_declines_short_series():
    idx = pd.date_range("2024-01-01", periods=200, freq="1D", tz="UTC")
    out = degradation(pd.Series(1.0, index=idx))
    assert "needs 2 years" in out


def test_daily_pi_excludes_low_coverage():
    from types import SimpleNamespace

    from triage.trend import daily_pi

    idx = pd.date_range("2024-01-01", periods=4, freq="1D", tz="UTC")
    daily = pd.DataFrame(
        {"pi": [1.0, 0.9, 0.8, 0.7], "coverage": [1.0, 0.5, 1.0, 1.0]}, index=idx
    )
    pi = daily_pi(daily, SimpleNamespace(coverage_min=0.8))
    assert len(pi) == 3 and 0.9 not in pi.values
