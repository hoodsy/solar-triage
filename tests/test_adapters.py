from types import SimpleNamespace

import pandas as pd

from triage.adapters import CsvAdapter, SourceFile, Stream


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
        meter=Stream(files=(SourceFile("m.csv"),), column="power"),
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
