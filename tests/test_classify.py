import numpy as np
import pandas as pd

from triage.classify import detect_soiling


def make_daily(pi_values) -> pd.DataFrame:
    idx = pd.date_range(
        "2024-01-01", periods=len(pi_values), freq="1D", tz="US/Pacific"
    )
    return pd.DataFrame({"pi": list(pi_values), "pi_baseline": 1.0}, index=idx)


# detect_soiling never reads intraday data, so None stands in for it.


def test_fires_on_gradual_decline():
    daily = make_daily(1.0 - 0.004 * np.arange(16))  # smooth -0.4%/day slide
    assert detect_soiling(daily.index[-1], None, daily) is not None


def test_rejects_single_step():
    daily = make_daily([1.0] * 12 + [0.85] * 4)  # flat, then one -15% step
    assert detect_soiling(daily.index[-1], None, daily) is None


def test_rejects_double_step():
    daily = make_daily([1.0] * 6 + [0.93] * 5 + [0.86] * 5)  # two -7% steps
    assert detect_soiling(daily.index[-1], None, daily) is None
