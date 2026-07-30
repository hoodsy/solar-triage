from types import SimpleNamespace

import pandas as pd

from triage.weather import OpenMeteoWeather


def make_site():
    return SimpleNamespace(
        lat=-36.85,
        lon=174.76,
        tilt=25.0,
        azimuth=0.0,
        tz="Pacific/Auckland",
        interval="15min",
    )


PAYLOAD = {
    "hourly": {
        "time": ["2025-10-09T00:00", "2025-10-09T01:00", "2025-10-09T02:00"],
        "global_tilted_irradiance": [0.0, 120.0, None],
    }
}


class FakeResponse:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return PAYLOAD


def test_fetch_parse_and_upsample(monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(params)
        return FakeResponse()

    import httpx

    monkeypatch.setattr(httpx, "get", fake_get)
    poa = OpenMeteoWeather(start="2025-10-09", end="2025-10-09").poa(make_site())

    # pvlib north (0) must be sent as Open-Meteo north (-180)
    assert calls[0]["azimuth"] == -180.0
    # UTC 01:00 == 14:00 NZDT; the hour mean fills its four quarter-hours
    for t in ("13:15", "13:30", "13:45", "14:00"):
        assert poa[pd.Timestamp(f"2025-10-09 {t}", tz="Pacific/Auckland")] == 120.0
    # a null hour stays NaN — never borrowed from a neighbouring hour
    assert pd.isna(poa[pd.Timestamp("2025-10-09 15:00", tz="Pacific/Auckland")])


def test_rejects_coarser_than_hourly_site(monkeypatch):
    import httpx

    monkeypatch.setattr(httpx, "get", lambda *a, **k: FakeResponse())
    site = make_site()
    site.interval = "2h"
    import pytest

    with pytest.raises(NotImplementedError):
        OpenMeteoWeather(start="2025-10-09", end="2025-10-09").poa(site)


def test_cache_roundtrip(tmp_path, monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(params)
        return FakeResponse()

    import httpx

    monkeypatch.setattr(httpx, "get", fake_get)
    weather = OpenMeteoWeather(start="2025-10-09", end="2025-10-09", cache_dir=tmp_path)
    site = make_site()

    poa1 = weather.poa(site)
    assert len(calls) == 1
    assert (tmp_path / "openmeteo_-36.85_174.76_2025-10-09_2025-10-09.csv").exists()

    def no_http(*args, **kwargs):
        raise AssertionError("HTTP hit despite cache")

    monkeypatch.setattr(httpx, "get", no_http)
    poa2 = weather.poa(site)  # served from disk
    assert list(poa1.index) == list(poa2.index)
    assert poa1.fillna(-1).tolist() == poa2.fillna(-1).tolist()
