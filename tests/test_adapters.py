from types import SimpleNamespace

import pandas as pd
import pytest

from triage.adapters import CsvAdapter, SolarNetworkAdapter, SourceFile, Stream


def make_site(tz="US/Pacific", interval="15min"):
    # adapters read only .tz and .interval from the site
    return SimpleNamespace(tz=tz, interval=interval)


def make_csv(dir, name, times, values, time_col="measured_on", col="power"):
    pd.DataFrame({time_col: times, col: values}).to_csv(dir / name, index=False)


def test_canonical_contract(tmp_path):
    make_csv(tmp_path, "m.csv", ["2024-06-01 12:00", "2024-06-01 12:15"], [100.0, 200.0])
    make_csv(tmp_path, "i.csv", ["2024-06-01 12:00", "2024-06-01 12:15"], [800.0, 900.0], col="poa")
    adapter = CsvAdapter(
        data_dir=tmp_path,
        meter=Stream(files=("m.csv",), column="power"),  # plain str -> SourceFile
        irradiance=Stream(files=(SourceFile("i.csv"),), column="poa"),
    )
    df = adapter.load(make_site())
    assert list(df.columns) == ["ac_power_kw", "poa_wm2"]
    assert df.index.name == "measured_on"
    assert str(df.index.tz) == "US/Pacific"
    assert df.index.is_unique and df.index.is_monotonic_increasing


def test_dedupe_keep_last(tmp_path):
    make_csv(tmp_path, "old.csv", ["2024-06-01 12:00"], [1.0])
    make_csv(tmp_path, "new.csv", ["2024-06-01 12:00"], [2.0])
    adapter = CsvAdapter(
        data_dir=tmp_path,
        meter=Stream(files=(SourceFile("old.csv"), SourceFile("new.csv")), column="power", keep="last"),
    )
    df = adapter.load(make_site())
    assert df["ac_power_kw"].iloc[0] == 2.0  # later file wins


def test_dedupe_keep_first(tmp_path):
    make_csv(tmp_path, "fine.csv", ["2024-06-01 12:00"], [1.0])
    make_csv(tmp_path, "coarse.csv", ["2024-06-01 12:00"], [2.0])
    adapter = CsvAdapter(
        data_dir=tmp_path,
        meter=Stream(files=(SourceFile("fine.csv"), SourceFile("coarse.csv")), column="power", keep="first"),
    )
    df = adapter.load(make_site())
    assert df["ac_power_kw"].iloc[0] == 1.0  # earlier file wins


def test_per_file_timezone(tmp_path):
    # 2024-06-01 19:00 UTC == 2024-06-01 12:00 US/Pacific (PDT, UTC-7)
    make_csv(tmp_path, "utc.csv", ["2024-06-01 19:00"], [5.0], time_col="utc_measured_on")
    adapter = CsvAdapter(
        data_dir=tmp_path,
        meter=Stream(
            files=(SourceFile("utc.csv", time_col="utc_measured_on", tz="UTC"),),
            column="power",
        ),
    )
    df = adapter.load(make_site())
    assert df.index[0] == pd.Timestamp("2024-06-01 12:00", tz="US/Pacific")


def test_ambiguous_fallback_stamp_dropped(tmp_path):
    # 2024-11-03 01:15 happened twice on the local clock; recorded once -> dropped
    make_csv(tmp_path, "m.csv", ["2024-11-03 01:15", "2024-11-03 12:00"], [1.0, 2.0])
    adapter = CsvAdapter(
        data_dir=tmp_path, meter=Stream(files=(SourceFile("m.csv"),), column="power")
    )
    df = adapter.load(make_site())
    assert len(df) == 1
    assert df.index[0].hour == 12


def test_resample_right_closed(tmp_path):
    make_csv(
        tmp_path, "i.csv",
        ["2024-06-01 12:05", "2024-06-01 12:10", "2024-06-01 12:15"],
        [1.0, 2.0, 3.0], col="poa",
    )
    make_csv(tmp_path, "m.csv", ["2024-06-01 12:15"], [100.0])
    adapter = CsvAdapter(
        data_dir=tmp_path,
        meter=Stream(files=(SourceFile("m.csv"),), column="power"),
        irradiance=Stream(files=(SourceFile("i.csv"),), column="poa", resample=True),
    )
    df = adapter.load(make_site())
    # (12:00, 12:15] averages into the 12:15 label
    assert df.loc[pd.Timestamp("2024-06-01 12:15", tz="US/Pacific"), "poa_wm2"] == 2.0
    assert df.loc[pd.Timestamp("2024-06-01 12:15", tz="US/Pacific"), "ac_power_kw"] == 100.0


def test_power_only_site(tmp_path):
    make_csv(tmp_path, "m.csv", ["2024-06-01 12:00"], [100.0])
    adapter = CsvAdapter(
        data_dir=tmp_path, meter=Stream(files=(SourceFile("m.csv"),), column="power")
    )
    df = adapter.load(make_site())
    assert list(df.columns) == ["ac_power_kw"]


def test_solarnetwork_mapping_and_pagination(monkeypatch):
    # recorded shape of /solarquery/api/v1/pub/datum/list, split into two pages
    pages = [
        {"data": {"totalResults": 3, "startingOffset": 0, "returnedResultCount": 2,
                  "results": [
                      {"created": "2026-07-28 00:00:00Z", "sourceId": "DB", "watts": 27375.8},
                      {"created": "2026-07-28 00:15:00Z", "sourceId": "DB", "watts": 25797.3},
                  ]}},
        {"data": {"totalResults": 3, "startingOffset": 2, "returnedResultCount": 1,
                  "results": [
                      {"created": "2026-07-28 00:30:00Z", "sourceId": "DB", "watts": 24000.0},
                  ]}},
    ]
    calls = []

    class FakeResponse:
        status_code = 200

        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self._payload

    def fake_get(url, params=None, timeout=None):
        calls.append(params)
        return FakeResponse(pages[len(calls) - 1])

    import httpx

    monkeypatch.setattr(httpx, "get", fake_get)
    adapter = SolarNetworkAdapter(node_id=120, power_source_id="Solar", lookback_days=1)
    df = adapter.load(make_site(tz="Pacific/Auckland"))

    assert len(calls) == 2  # pagination followed to totalResults
    assert len(df) == 3
    assert df.index.name == "measured_on"
    # 2026-07-28 00:00 UTC == 12:00 NZST, +15min start->end label shift
    assert df.index[0] == pd.Timestamp("2026-07-28 12:15", tz="Pacific/Auckland")
    assert df["ac_power_kw"].iloc[0] == pytest.approx(27.3758)
    # request params must be UTC (the API interprets startDate/endDate as UTC)
    assert calls[0]["aggregation"] == "FifteenMinute"


def test_solarnetwork_fixed_window_cache(tmp_path, monkeypatch):
    page = {"data": {"totalResults": 1, "startingOffset": 0, "returnedResultCount": 1,
                     "results": [
                         {"created": "2026-06-01 00:00:00Z", "sourceId": "Solar", "watts": 1500.0},
                     ]}}
    calls = []

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return page

    def fake_get(url, params=None, timeout=None):
        calls.append(params)
        return FakeResponse()

    import httpx

    monkeypatch.setattr(httpx, "get", fake_get)
    adapter = SolarNetworkAdapter(
        node_id=120, power_source_id="Solar",
        start="2026-06-01", end="2026-06-02", cache_dir=tmp_path,
    )
    site = make_site(tz="Pacific/Auckland")

    df1 = adapter.load(site)
    assert len(calls) == 1  # fetched over HTTP once
    assert (tmp_path / "node120_Solar_2026-06-01_2026-06-02.csv").exists()

    def no_http(*args, **kwargs):
        raise AssertionError("HTTP hit despite cache")

    monkeypatch.setattr(httpx, "get", no_http)
    df2 = adapter.load(site)  # served from disk
    assert list(df1.index) == list(df2.index)
    assert df1["ac_power_kw"].tolist() == df2["ac_power_kw"].tolist()


def test_temperature_stream_converts_fahrenheit(tmp_path):
    make_csv(tmp_path, "meter.csv", ["2024-06-01 12:00", "2024-06-01 12:15"], [1.0, 1.0])
    make_csv(
        tmp_path, "env.csv",
        ["2024-06-01 12:00", "2024-06-01 12:15"], [95.0, 96.8],
        col="ambient_temperature_o_1",
    )
    adapter = CsvAdapter(
        data_dir=tmp_path,
        meter=Stream(files=("meter.csv",), column="power"),
        temperature=Stream(
            files=("env.csv",), column="ambient_temperature_o_1", fahrenheit=True
        ),
    )
    df = adapter.load(make_site())
    assert abs(df["temp_c"].iloc[0] - 35.0) < 0.01  # 95 F
    assert abs(df["temp_c"].iloc[1] - 36.0) < 0.01  # 96.8 F
