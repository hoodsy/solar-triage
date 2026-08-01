import pandas as pd

from triage.classify import Fault
from triage.train.export import COLUMNS, HEALTHY, export_training, training_frame


def make_daily(n_days=4):
    idx = pd.date_range("2024-06-01", periods=n_days, freq="1D", tz="US/Pacific")
    return pd.DataFrame(
        {
            "actual_kwh": 100.0,
            "expected_kwh": 110.0,
            "coverage": 1.0,
            "pi": 0.91,
            "pi_baseline": 0.95,
            "flagged": [False, True, True, False],
        },
        index=idx,
    )


def make_frames(daily, verdicts=None):
    """Classifier + final frames on daily's flagged days (rows 1 and 2)."""
    idx = daily.index[[1, 2]].rename("date")
    result = pd.DataFrame(
        {
            "label": [Fault.UNCLASSIFIED, Fault.OUTAGE],
            "pi": 0.5,
            "evidence": ["step", "dead run"],
        },
        index=idx,
    )
    final = result.copy()
    if verdicts is not None:
        final["label"] = [Fault.OUTAGE, Fault.OUTAGE]  # referee attributed row 1
        final["verdict"] = verdicts
    return result, final


def test_schema_and_healthy_days():
    daily = make_daily()
    result, final = make_frames(daily)
    out = training_frame(daily, result, final, "t1")
    assert list(out.columns) == COLUMNS
    assert len(out) == 4
    assert (out["site"] == "t1").all()
    assert out["rain_mm"].isna().all()  # column present without a rain stream
    healthy = out[~out["flagged"]]
    assert (healthy["rule_label"] == HEALTHY).all()
    assert (healthy["final_label"] == HEALTHY).all()
    assert (healthy["evidence"] == "").all()


def test_rule_only_site_provenance():
    daily = make_daily()
    result, final = make_frames(daily)  # no verdict column: no sub-metering
    out = training_frame(daily, result, final, "t1")
    assert (out["provenance"] == "rule").all()
    assert (out["verdict"] == "").all()
    assert out.iloc[2]["rule_label"] == "outage"  # StrEnum serialized as value


def test_referee_gold_vs_uncheckable():
    daily = make_daily()
    result, final = make_frames(daily, verdicts=["attributed", "uncheckable"])
    out = training_frame(daily, result, final, "t1")
    # attributed: referee gold, final label upgraded past the rule label
    assert out.iloc[1]["rule_label"] == "unclassified"
    assert out.iloc[1]["final_label"] == "outage"
    assert out.iloc[1]["provenance"] == "referee"
    # uncheckable: label rests on rule evidence alone
    assert out.iloc[2]["provenance"] == "rule"
    assert out[~out["flagged"]]["provenance"].eq("rule").all()


def test_export_writes_sitename_timestamp_csv(tmp_path):
    daily = make_daily()
    result, final = make_frames(daily, verdicts=["attributed", "confirmed"])
    path = export_training(daily, result, final, "t1", out_dir=tmp_path)
    assert path.parent == tmp_path / "t1"
    assert path.name.startswith("t1-") and path.suffix == ".csv"
    back = pd.read_csv(path, index_col="date")
    assert list(back.columns) == COLUMNS
    assert back.iloc[1]["final_label"] == "outage"
