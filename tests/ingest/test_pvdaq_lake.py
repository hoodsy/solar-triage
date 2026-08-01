from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from triage.ingest import LakeColumn, PvdaqLakeAdapter

# metric ids as in the real lake: the __NNNN suffix of the wide-CSV columns
M_AC, M_POA, M_TEMP, M_INV1, M_INV2 = 1, 2, 3, 4, 5


@pytest.fixture
def lake_dir(tmp_path):
    """Two day-partitions of long-format 1-min rows, lake chaos included:
    power in W, temp in °F, and two inverter channels."""
    values = {M_AC: 5000.0, M_POA: 800.0, M_TEMP: 77.0, M_INV1: 2500.0, M_INV2: 2500.0}
    for day in ("2021-06-01", "2021-06-02"):
        idx = pd.date_range(f"{day} 00:00", periods=1440, freq="1min")
        long = pd.concat(
            pd.DataFrame(
                {"measured_on": idx, "metric_id": m, "value": v}
            )
            for m, v in values.items()
        )
        d = pd.Timestamp(day)
        part = tmp_path / f"year={d.year}" / f"month={d.month}" / f"day={d.day}"
        part.mkdir(parents=True)
        long.to_parquet(part / f"system_1__date_{day}.snappy.000.parquet")
    return tmp_path


SITE = SimpleNamespace(
    tz="US/Eastern",
    interval="15min",
    electrical=(str(M_INV1), str(M_INV2)),
)


def make_adapter(lake_dir: Path) -> PvdaqLakeAdapter:
    return PvdaqLakeAdapter(
        data_dir=lake_dir,
        meter=LakeColumn(M_AC, scale=0.001),
        irradiance=LakeColumn(M_POA),
        temperature=LakeColumn(M_TEMP, offset=-32.0, scale=5 / 9),
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
    # poison an interior hour (minutes 60-119) of the meter channel with -999;
    # a leading-edge gap would just shorten the span (pivot drops all-NaN rows)
    part = next((lake_dir / "year=2021" / "month=6" / "day=1").glob("*.parquet"))
    df = pd.read_parquet(part)
    meter_rows = df.index[df["metric_id"] == M_AC][60:120]
    df.loc[meter_rows, "value"] = -999.0
    df.to_parquet(part)
    out = make_adapter(lake_dir).load(SITE)
    gap = out["ac_power_kw"].loc[
        "2021-06-01 01:15:00-04:00":"2021-06-01 01:45:00-04:00"
    ]
    assert gap.isna().all()  # masked, not scaled into a plausible -0.999 kW
    assert out["ac_power_kw"].dropna().iloc[0] == pytest.approx(5.0)


def test_missing_channel_is_nan_not_error(lake_dir):
    adapter = PvdaqLakeAdapter(
        data_dir=lake_dir,
        meter=LakeColumn(M_AC, scale=0.001),
        irradiance=LakeColumn(999),  # never recorded by this system
    )
    df = adapter.load(SITE)
    assert df["poa_wm2"].isna().all()
    assert df["ac_power_kw"].notna().any()


def test_load_inverters_fleet_order(lake_dir):
    inv = make_adapter(lake_dir).load_inverters(SITE)
    assert list(inv.columns) == ["inv_01", "inv_02"]
    assert inv["inv_01"].dropna().iloc[0] == pytest.approx(2.5)
    assert str(inv.index.tz) == "US/Eastern"


def test_multi_meter_sum_nan_when_half_missing(lake_dir):
    # two 2.5 kW halves summed; nothing else configured
    adapter = PvdaqLakeAdapter(
        data_dir=lake_dir,
        meter=(LakeColumn(M_INV1, scale=0.001), LakeColumn(M_INV2, scale=0.001)),
    )
    out = adapter.load(SITE)
    assert out["ac_power_kw"].dropna().iloc[0] == pytest.approx(5.0)
    # kill one half for an interior hour: the sum must go NaN, not halve
    part = next((lake_dir / "year=2021" / "month=6" / "day=1").glob("*.parquet"))
    df = pd.read_parquet(part)
    inv1_rows = df.index[df["metric_id"] == M_INV1]
    df = df.drop(inv1_rows[60:120])
    df.to_parquet(part)
    out = adapter.load(SITE)
    gap = out["ac_power_kw"].loc[
        "2021-06-01 01:15:00-04:00":"2021-06-01 01:45:00-04:00"
    ]
    assert gap.isna().all()


def test_unit_break_eras_convert_piecewise(lake_dir):
    # day 1 raw is "hectowatts", day 2 the logger swapped to W
    adapter = PvdaqLakeAdapter(
        data_dir=lake_dir,
        meter=LakeColumn(M_AC, scale=0.1, breaks=(("2021-06-02", 0.0, 0.001),)),
    )
    out = adapter.load(SITE)["ac_power_kw"].dropna()
    assert out.loc["2021-06-01 12:00:00-04:00"] == pytest.approx(500.0)  # 5000 hW
    assert out.loc["2021-06-02 12:00:00-04:00"] == pytest.approx(5.0)  # 5000 W
