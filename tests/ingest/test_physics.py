from types import SimpleNamespace

import pandas as pd

from triage.ingest.physics import clearsky_poa, expected_kw


def test_expected_kw_formula():
    poa = pd.Series([0.0, 500.0, 1000.0])
    site = SimpleNamespace(dc_capacity_kw=100.0, derate=0.8)
    assert expected_kw(poa, site).tolist() == [0.0, 40.0, 80.0]


def test_clearsky_poa_shape():
    idx = pd.date_range("2024-06-01", periods=96, freq="15min", tz="Pacific/Auckland")
    site = SimpleNamespace(
        lat=-36.9, lon=174.8, tilt=25.0, azimuth=0.0, tz="Pacific/Auckland"
    )
    poa = clearsky_poa(idx, site)
    assert (poa.fillna(0) >= 0).all()
    assert (poa.between_time("00:00", "03:00").fillna(0) < 1.0).all()  # dark night
    assert poa.idxmax().hour in range(10, 15)  # peak lands midday


def test_low_light_saturation_derates_dim_not_bright():
    import pandas as pd
    from types import SimpleNamespace
    from triage.ingest.physics import expected_kw

    poa = pd.Series([50.0, 150.0, 1000.0])
    flat = SimpleNamespace(dc_capacity_kw=100.0, derate=0.8, low_light_k=0.0)
    curved = SimpleNamespace(dc_capacity_kw=100.0, derate=0.8, low_light_k=55.0)
    base = expected_kw(poa, flat)
    adj = expected_kw(poa, curved)
    assert adj.iloc[2] == base.iloc[2]  # full sun untouched
    assert adj.iloc[0] / base.iloc[0] < 0.55  # deep dim heavily derated
    assert 0.7 < adj.iloc[1] / base.iloc[1] < 0.85
