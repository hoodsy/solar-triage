from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from triage.train.features import FEATURE_COLUMNS, day_features
from triage.train.splits import assign_events, event_split, leave_one_site_out

SITE = SimpleNamespace(
    dc_capacity_kw=10.0, ac_capacity_kw=9.0, n_units=4, interval="15min"
)


def make_day(tz="US/Eastern"):
    day = pd.Timestamp("2024-06-01", tz=tz)
    idx = pd.date_range(day, periods=96, freq="15min")
    hours = (idx.hour + idx.minute / 60).values
    bell = np.clip(np.sin((hours - 6) * np.pi / 12), 0, None) * 9.0
    df = pd.DataFrame(
        {
            "ac_power_kw": bell * 0.9,
            "expected_kw": bell,
            "clearsky_kw": bell * 1.1,
            "temp_c": 20.0,
        },
        index=idx,
    )
    daily = pd.DataFrame(
        {"pi": 0.9, "pi_baseline": 1.0, "coverage": 1.0, "snow_cm": 0.0},
        index=pd.DatetimeIndex([day]),
    )
    return day, df, daily


def test_day_features_complete_and_sane():
    day, df, daily = make_day()
    f = day_features(day, df, daily, SITE)
    assert set(f) == set(FEATURE_COLUMNS)
    assert f["pi_rel"] == pytest.approx(0.9)
    assert f["csr"] == pytest.approx(0.9 / 1.1, abs=0.01)
    assert f["model_csr"] == pytest.approx(1 / 1.1, abs=0.01)
    assert f["chop"] < 0.02  # smooth bell
    assert f["dead_run_h"] == 0.0
    assert f["snow_7d"] == 0.0
    assert -1 <= f["doy_sin"] <= 1


def test_day_features_nan_when_unmeasurable():
    day, df, daily = make_day()
    f = day_features(day, df.drop(columns=["temp_c"]), daily, SITE)
    assert pd.isna(f["tmax_c"]) and pd.isna(f["temp_corr"])
    assert pd.isna(f["pi_slope_14d"])  # not enough trailing history
    empty = day_features(day, df.iloc[0:0], daily, SITE)
    assert pd.isna(empty["csr"]) and pd.notna(empty["doy_sin"])


def make_labeled(site, labels, start):
    d = pd.date_range(start, periods=len(labels), freq="1D")
    return pd.DataFrame({"site": site, "date": d, "final_label": labels})


def test_events_group_consecutive_same_label():
    df = pd.concat(
        [
            make_labeled("a", ["outage"] * 3 + ["healthy"] * 2, "2024-01-01"),
            make_labeled("b", ["outage"] * 2, "2024-01-01"),
        ],
        ignore_index=True,
    )
    ev = assign_events(df)
    assert ev.nunique() == 3  # a:outage-run, a:healthy-run, b:outage-run
    assert ev.iloc[0] == ev.iloc[2] and ev.iloc[0] != ev.iloc[3]
    assert ev.iloc[0] != ev.iloc[5]  # same label, different site


def test_event_split_never_straddles_and_is_deterministic():
    labels = (["outage"] * 5 + ["healthy"] * 10) * 40
    df = make_labeled("a", labels, "2020-01-01")
    mask = event_split(df, test_frac=0.3)
    ev = assign_events(df)
    per_event = mask.groupby(ev).nunique()
    assert (per_event == 1).all()  # every event fully on one side
    assert 0.1 < mask.mean() < 0.5  # roughly the requested fraction
    assert mask.equals(event_split(df, test_frac=0.3))  # deterministic
    assert not mask.equals(event_split(df, test_frac=0.3, salt="fold2"))


def test_leave_one_site_out_covers_everything():
    df = pd.concat(
        [make_labeled(s, ["healthy"] * 4, "2024-01-01") for s in ("a", "b", "c")],
        ignore_index=True,
    )
    folds = dict(leave_one_site_out(df))
    assert set(folds) == {"a", "b", "c"}
    total_test = sum(m.sum() for m in folds.values())
    assert total_test == len(df)  # every row held out exactly once
    for site, m in folds.items():
        assert (df.loc[m, "site"] == site).all()


def test_train_build_matrix_and_smoke_fit():
    from triage.train.model import FEATURES, build_matrix, make_model

    n = 400
    rng = np.random.default_rng(3)
    df = pd.DataFrame(rng.normal(size=(n, len(FEATURES))), columns=FEATURES)
    df["final_label"] = np.where(df["csr"] > 0, "healthy", "outage")
    df["provenance"] = np.where(rng.random(n) < 0.1, "referee", "rule")
    X, y, w = build_matrix(df)
    assert len(X) == len(y) == len(w) == n
    # referee rows weigh GOLD_WEIGHT x their class's rule rows
    for lbl in ("healthy", "outage"):
        g = w[(df["final_label"] == lbl) & (df["provenance"] == "referee")]
        r = w[(df["final_label"] == lbl) & (df["provenance"] == "rule")]
        if len(g) and len(r):
            assert g.iloc[0] / r.iloc[0] == pytest.approx(5.0)
    model = make_model()
    model.set_params(max_iter=20)
    model.fit(X, y, sample_weight=w)
    assert (model.predict(X) == y).mean() > 0.95  # separable by construction
