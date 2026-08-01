from types import SimpleNamespace

import numpy as np
import pandas as pd

from triage.classify.referee import daily_divergence, resolve

REF_SITE = SimpleNamespace(n_units=4, ac_capacity_kw=4.0, interval="15min")


def make_inv_kw(n_days=40, n_inv=4, dead=None):
    """Synthetic fleet: 1 kW daytime each; `dead` = {inv: [day_indices]}."""
    idx = pd.date_range(
        "2024-06-01", periods=n_days * 96, freq="15min", tz="US/Pacific"
    )
    df = pd.DataFrame(
        0.0, index=idx, columns=[f"inv_{i + 1:02d}" for i in range(n_inv)]
    )
    daylight = (idx.hour >= 8) & (idx.hour < 16)
    df.loc[daylight, :] = 1.0
    for inv, day_idxs in (dead or {}).items():
        for d in day_idxs:
            day = idx[0].normalize() + pd.Timedelta(days=d)
            df.loc[day : day + pd.Timedelta("23h45min"), inv] = 0.0
    return df


def make_result(labels_by_day, ref):
    """Claim frame on ref's (tz-aware) day index: {day_idx: label}."""
    idx = pd.DatetimeIndex([ref.index[d] for d in labels_by_day], name="date")
    return pd.DataFrame(
        {"label": list(labels_by_day.values()), "pi": 0.5, "evidence": "step"},
        index=idx,
    )


def test_dead_inverter_diverges():
    ref = daily_divergence(make_inv_kw(dead={"inv_03": [35, 36]}))
    assert ref.iloc[35]["n_divergent"] == 1
    assert ref.iloc[35]["divergent"] == ["inv_03"]
    assert ref.iloc[20]["n_divergent"] == 0


def test_fleet_uniform_day_shows_no_divergence():
    inv = make_inv_kw()
    day = inv.index[0].normalize() + pd.Timedelta(days=35)
    inv.loc[day : day + pd.Timedelta("23h45min")] *= 0.6  # everyone sags: heat
    ref = daily_divergence(inv)
    assert ref.iloc[35]["n_divergent"] == 0


def test_resolve_verdicts_on_claims():
    ref = daily_divergence(make_inv_kw(dead={"inv_03": [35]}))
    final = resolve(make_result({35: "outage", 20: "thermal"}, ref), ref, REF_SITE)
    assert final.iloc[0]["verdict"] == "confirmed"  # outage with divergence
    assert final.iloc[1]["verdict"] == "confirmed"  # thermal, none divergent
    final2 = resolve(make_result({35: "thermal"}, ref), ref, REF_SITE)
    assert final2.iloc[0]["verdict"] == "refuted"  # the dead inverter IS the story


def test_cloudy_day_with_standing_fault_does_not_refute_weather():
    inv = make_inv_kw(dead={"inv_03": list(range(30, 40))})  # standing fault
    day = inv.index[0].normalize() + pd.Timedelta(days=35)
    healthy = [c for c in inv.columns if c != "inv_03"]
    inv.loc[day : day + pd.Timedelta("23h45min"), healthy] *= 0.4  # clouds
    ref = daily_divergence(inv)
    final = resolve(make_result({35: "weather"}, ref), ref, REF_SITE)
    assert final.iloc[0]["verdict"] == "confirmed"  # clouds dominate the deficit


def test_total_outage_confirmed_by_fleet_collapse():
    inv = make_inv_kw()
    day = inv.index[0].normalize() + pd.Timedelta(days=35)
    inv.loc[day : day + pd.Timedelta("23h45min")] = 0.0  # whole plant dark
    ref = daily_divergence(inv)
    final = resolve(make_result({35: "outage"}, ref), ref, REF_SITE)
    assert final.iloc[0]["verdict"] == "confirmed"


def test_resolve_attributes_unclassified():
    inv = make_inv_kw(dead={"inv_03": [35]})
    day36 = inv.index[0].normalize() + pd.Timedelta(days=36)
    inv.loc[day36 : day36 + pd.Timedelta("23h45min")] *= 0.3  # plant-wide
    ref = daily_divergence(inv)
    result = make_result({35: "unclassified", 36: "unclassified"}, ref)
    final = resolve(result, ref, REF_SITE)
    assert final.iloc[0]["label"] == "outage"  # inv_03 explains the shortfall
    assert "1/4 inverters" in final.iloc[0]["evidence"]
    assert final.iloc[0]["verdict"] == "attributed"
    assert final.iloc[1]["label"] == "outage"  # fleet collapse
    assert "plant-wide" in final.iloc[1]["evidence"]
    # shape contract for events(): index and pi survive
    assert final.index.equals(result.index)
    assert (final["pi"] == 0.5).all()


def test_underexplained_day_gets_residual_primary_plus_outage_secondary():
    inv = make_inv_kw(dead={"inv_03": [35]})
    day = inv.index[0].normalize() + pd.Timedelta(days=35)
    healthy = [c for c in inv.columns if c != "inv_03"]
    inv.loc[day : day + pd.Timedelta("23h45min"), healthy] *= 0.55  # big uniform dip
    ref = daily_divergence(inv)
    # without df the residual is unnameable: primary stays unclassified
    final = resolve(make_result({35: "unclassified"}, ref), ref, REF_SITE)
    assert final.iloc[0]["label"] == "unclassified"
    assert final.iloc[0]["label_2"] == "outage"
    assert final.iloc[0]["verdict"] == "attributed"
    assert "fleet-wide" in final.iloc[0]["evidence"]
    # with a dim intraday the residual is named weather
    idx = pd.date_range(day + pd.Timedelta("8h"), periods=40, freq="15min")
    df = pd.DataFrame(
        {"ac_power_kw": 1.0, "clearsky_kw": 3.0},  # 33% of clear ceiling
        index=idx,
    )
    final = resolve(make_result({35: "unclassified"}, ref), ref, REF_SITE, df)
    assert final.iloc[0]["label"] == "weather"
    assert final.iloc[0]["label_2"] == "outage"


def test_divergence_without_plant_shortfall_is_not_split():
    # inv_03 relatively low but still ABOVE its own trailing norm while the
    # others over-produce: nobody is short, div_share is NaN — "loss plus
    # fleet-wide" is unjustified (the 135-row mixed artifact)
    inv = make_inv_kw()
    day = inv.index[0].normalize() + pd.Timedelta(days=35)
    span = slice(day, day + pd.Timedelta("23h45min"))
    healthy = [c for c in inv.columns if c != "inv_03"]
    inv.loc[span, healthy] *= 1.5
    inv.loc[span, "inv_03"] *= 1.2  # relatively divergent, absolutely fine
    ref = daily_divergence(inv)
    final = resolve(make_result({35: "unclassified"}, ref), ref, REF_SITE)
    assert final.iloc[0]["label"] == "unclassified"
    assert final.iloc[0]["label_2"] is None
    assert final.iloc[0]["verdict"] == "uncheckable"


def test_resolve_curtailment_needs_bright_flat_zero_divergence():
    ref = daily_divergence(make_inv_kw())
    day = ref.index[35]
    # bright flat clamp at 70% of ceiling across the whole midday window
    idx = pd.date_range(day + pd.Timedelta("8h"), periods=40, freq="15min")
    df = pd.DataFrame(
        {
            "ac_power_kw": 0.7 * REF_SITE.ac_capacity_kw,
            "clearsky_kw": np.linspace(2.0, 3.0, 40),
        },
        index=idx,
    )
    final = resolve(make_result({35: "unclassified"}, ref), ref, REF_SITE, df)
    assert final.iloc[0]["label"] == "curtailment"
    assert final.iloc[0]["verdict"] == "attributed"


def test_resolve_empty_result_keeps_schema():
    ref = daily_divergence(make_inv_kw())
    empty = pd.DataFrame(
        columns=["label", "pi", "evidence"],
        index=pd.DatetimeIndex([], name="date"),
    )
    final = resolve(empty, ref, REF_SITE)
    assert list(final.columns) == ["label", "pi", "evidence", "label_2", "verdict"]
    assert final.empty
