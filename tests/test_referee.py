import pandas as pd

from triage.referee import cross_check, daily_divergence


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


def test_cross_check_verdicts():
    ref = daily_divergence(make_inv_kw(dead={"inv_03": [35]}))
    dates = [ref.index[35], ref.index[20]]
    result = pd.DataFrame(
        {"label": ["outage", "thermal"], "pi": 0.5, "evidence": "e"},
        index=pd.DatetimeIndex(dates, name="date"),
    )
    verdicts = cross_check(result, ref)
    assert verdicts.iloc[0]["verdict"] == "confirmed"  # outage with divergence
    assert verdicts.iloc[1]["verdict"] == "confirmed"  # thermal, none divergent
    result2 = result.copy()
    result2.iloc[0, result2.columns.get_loc("label")] = "thermal"
    assert cross_check(result2, ref).iloc[0]["verdict"] == "refuted"


def test_cloudy_day_with_standing_fault_does_not_refute_weather():
    inv = make_inv_kw(dead={"inv_03": list(range(30, 40))})  # standing fault
    day = inv.index[0].normalize() + pd.Timedelta(days=35)
    healthy = [c for c in inv.columns if c != "inv_03"]
    inv.loc[day : day + pd.Timedelta("23h45min"), healthy] *= 0.4  # clouds
    ref = daily_divergence(inv)
    result = pd.DataFrame(
        {"label": ["weather"], "pi": 0.4, "evidence": "e"},
        index=pd.DatetimeIndex([ref.index[35]], name="date"),
    )
    v = cross_check(result, ref)
    assert v.iloc[0]["verdict"] == "confirmed"  # clouds dominate the deficit


def test_clear_day_fault_still_refutes_weather():
    ref = daily_divergence(make_inv_kw(n_inv=4, dead={"inv_03": [35]}))
    result = pd.DataFrame(
        {"label": ["weather"], "pi": 0.7, "evidence": "e"},
        index=pd.DatetimeIndex([ref.index[35]], name="date"),
    )
    v = cross_check(result, ref)
    assert v.iloc[0]["verdict"] == "refuted"  # the dead inverter IS the story


def test_total_outage_confirmed_by_fleet_collapse():
    inv = make_inv_kw()
    day = inv.index[0].normalize() + pd.Timedelta(days=35)
    inv.loc[day : day + pd.Timedelta("23h45min")] = 0.0  # whole plant dark
    ref = daily_divergence(inv)
    result = pd.DataFrame(
        {"label": ["outage"], "pi": 0.05, "evidence": "e"},
        index=pd.DatetimeIndex([ref.index[35]], name="date"),
    )
    assert cross_check(result, ref).iloc[0]["verdict"] == "confirmed"


def test_resolve_attributes_unclassified():
    from types import SimpleNamespace

    from triage.referee import resolve

    inv = make_inv_kw(dead={"inv_03": [35]})
    day36 = inv.index[0].normalize() + pd.Timedelta(days=36)
    inv.loc[day36 : day36 + pd.Timedelta("23h45min")] *= 0.3  # plant-wide
    ref = daily_divergence(inv)
    result = pd.DataFrame(
        {"label": ["unclassified"] * 2, "pi": 0.5, "evidence": "step"},
        index=pd.DatetimeIndex([ref.index[35], ref.index[36]], name="date"),
    )
    final = resolve(result, ref, SimpleNamespace(n_units=4, ac_capacity_kw=4.0))
    assert final.iloc[0]["label"] == "outage"  # inv_03 explains the shortfall
    assert "1/4 inverters" in final.iloc[0]["evidence"]
    assert final.iloc[1]["label"] == "outage"  # fleet collapse
    assert "plant-wide" in final.iloc[1]["evidence"]
