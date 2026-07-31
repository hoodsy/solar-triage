from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from triage.adapters import LakeColumn, PvdaqLakeAdapter


@pytest.fixture
def lake_dir(tmp_path):
    """Two day-partitions of 1-min data, prize-lake column chaos included:
    power in W, temp in °F, a -999 sentinel, and two inverter channels."""
    for day in ("2021-06-01", "2021-06-02"):
        idx = pd.date_range(f"{day} 00:00", periods=1440, freq="1min")
        df = pd.DataFrame(
            {
                "measured_on": idx,
                "ac_power__1": 5000.0,  # W
                "poa_irradiance__2": 800.0,
                "ambient_temp_f__3": 77.0,  # °F -> 25 °C
                "inv1_ac_power__4": 2500.0,
                "inv2_ac_power__5": 2500.0,
            }
        )
        d = pd.Timestamp(day)
        part = tmp_path / f"year={d.year}" / f"month={d.month}" / f"day={d.day}"
        part.mkdir(parents=True)
        df.to_parquet(part / f"system_1__date_{day}.snappy.000.parquet")
    return tmp_path


SITE = SimpleNamespace(
    tz="US/Eastern",
    interval="15min",
    electrical=("inv1_ac_power__4", "inv2_ac_power__5"),
)


def make_adapter(lake_dir: Path) -> PvdaqLakeAdapter:
    return PvdaqLakeAdapter(
        data_dir=lake_dir,
        meter=LakeColumn("ac_power__1", scale=0.001),
        irradiance=LakeColumn("poa_irradiance__2"),
        temperature=LakeColumn("ambient_temp_f__3", offset=-32.0, scale=5 / 9),
        inverter_scale=0.001,
    )


def test_load_canonical_contract(lake_dir):
    df = make_adapter(lake_dir).load(SITE)
    assert list(df.columns) == ["ac_power_kw", "poa_wm2", "temp_c"]
    assert str(df.index.tz) == "US/Eastern"
    assert df.index.name == "measured_on"
    step = df.index[1] - df.index[0]
    assert step == pd.Timedelta("15min")
    assert df["ac_power_kw"].dropna().iloc[0] == pytest.approx(5.0)
    assert df["temp_c"].dropna().iloc[0] == pytest.approx(25.0)
    # label = END of interval: the 00:00 raw stamp closes the midnight bin,
    # and 00:01-00:15 land in the bin labeled 00:15
    assert df.index[0] == pd.Timestamp("2021-06-01 00:00", tz="US/Eastern")
    assert df.index[1] == pd.Timestamp("2021-06-01 00:15", tz="US/Eastern")


def test_sentinels_masked_before_conversion(lake_dir):
    # poison one raw file with a -999 run, reload
    part = next(lake_dir.rglob("*.parquet"))
    df = pd.read_parquet(part)
    df.loc[:59, "ac_power__1"] = -999.0
    df.to_parquet(part)
    out = make_adapter(lake_dir).load(SITE)
    hour1 = out["ac_power_kw"].iloc[:4]
    assert hour1.isna().all()  # masked, not scaled into a plausible -0.999 kW
    assert out["ac_power_kw"].dropna().iloc[0] == pytest.approx(5.0)


def test_load_inverters_fleet_order(lake_dir):
    inv = make_adapter(lake_dir).load_inverters(SITE)
    assert list(inv.columns) == ["inv_01", "inv_02"]
    assert inv["inv_01"].dropna().iloc[0] == pytest.approx(2.5)
    assert str(inv.index.tz) == "US/Eastern"
