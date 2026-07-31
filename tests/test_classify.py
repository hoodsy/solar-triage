from types import SimpleNamespace

import numpy as np
import pandas as pd

from triage.classify import Fault, classify_day, detect_soiling


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
