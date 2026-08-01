from types import SimpleNamespace

import numpy as np
import pandas as pd

from triage.ingest.quality import clean

QA_SITE = SimpleNamespace(ac_capacity_kw=200.0)


def make_df(ac=None, poa=None, temp=None, n=96):
    idx = pd.date_range("2024-06-01", periods=n, freq="15min", tz="US/Pacific")
    df = pd.DataFrame(index=idx)
    df["ac_power_kw"] = ac if ac is not None else np.sin(np.arange(n) / 8) ** 2 * 100
    if poa is not None:
        df["poa_wm2"] = poa
    if temp is not None:
        df["temp_c"] = temp
    return df


def test_stuck_nonzero_meter_masked():
    ac = np.sin(np.arange(96) / 8) ** 2 * 100 + 1
    ac[40:60] = 55.5  # frozen at a nonzero value
    out, masked = clean(make_df(ac=ac), QA_SITE)
    assert masked.get("meter stale", 0) > 10
    assert out["ac_power_kw"].iloc[45:59].isna().all()


def test_zero_flatline_preserved():
    # a dead plant flatlines at 0.0 — that is outage evidence, never masked
    ac = np.concatenate([np.zeros(48), np.sin(np.arange(48) / 8) ** 2 * 100])
    out, masked = clean(make_df(ac=ac), QA_SITE)
    assert "meter stale" not in masked
    assert (out["ac_power_kw"].iloc[:48] == 0).all()


def test_negative_poa_masked():
    poa = np.full(96, 500.0)
    poa[10:14] = -296.0  # 9069's broken reference cell
    poa[50] = -3.0  # normal thermopile night offset: kept
    out, masked = clean(make_df(poa=poa), QA_SITE)
    assert masked["poa negative"] == 4
    assert out["poa_wm2"].iloc[10:14].isna().all()
    assert out["poa_wm2"].iloc[50] == -3.0


def test_temp_out_of_range_masked():
    temp = np.full(96, 25.0)
    temp[5] = 87.0  # sensor glitch
    out, masked = clean(make_df(temp=temp), QA_SITE)
    assert masked["temp out of range"] == 1
    assert np.isnan(out["temp_c"].iloc[5])


def test_ceiling_flatline_preserved():
    # clipping physics: a flatline at the AC ceiling is never "stale"
    ac = np.sin(np.arange(96) / 8) ** 2 * 150
    ac[40:60] = 199.5  # pinned at the 200 kW ceiling for 5 hours
    out, masked = clean(make_df(ac=ac), QA_SITE)
    assert "meter stale" not in masked
    assert (out["ac_power_kw"].iloc[40:60] == 199.5).all()
