from types import SimpleNamespace

import numpy as np
import pandas as pd

from triage.classify import (
    Fault,
    chop_mad,
    classify_day,
    day_csr,
    detect_soiling,
    detect_thermal,
    detect_weather,
    events,
    unit_deficit,
)


def make_daily(pi_values) -> pd.DataFrame:
    idx = pd.date_range(
        "2024-01-01", periods=len(pi_values), freq="1D", tz="US/Pacific"
    )
    return pd.DataFrame({"pi": list(pi_values), "pi_baseline": 1.0}, index=idx)


# detect_soiling reads neither intraday data nor site config, so None stands
# in for both — the uniform detector signature is the only reason they exist.


def test_fires_on_gradual_decline():
    daily = make_daily(1.0 - 0.004 * np.arange(16))  # smooth -0.4%/day slide
    assert detect_soiling(daily.index[-1], None, daily, None) is not None


def test_rejects_single_step():
    daily = make_daily([1.0] * 12 + [0.85] * 4)  # flat, then one -15% step
    assert detect_soiling(daily.index[-1], None, daily, None) is None


def test_rejects_double_step():
    daily = make_daily([1.0] * 6 + [0.93] * 5 + [0.86] * 5)  # two -7% steps
    assert detect_soiling(daily.index[-1], None, daily, None) is None


def test_low_coverage_day_labeled_data_gap():
    daily = make_daily([1.0] * 5)
    daily["coverage"] = [1.0, 1.0, 0.5, 1.0, 1.0]
    site = SimpleNamespace(coverage_min=0.8)
    label, evidence = classify_day(daily.index[2], None, daily, site)
    assert label == Fault.DATA_GAP
    assert "50%" in evidence


def make_intraday(actual, expected, clearsky=None, temp=None, tz="UTC"):
    """One synthetic day on a 15-min grid from hourly values (07:00 onward)."""
    hours = pd.date_range("2025-01-15 07:00", periods=len(actual), freq="1h", tz=tz)
    idx = pd.date_range(hours[0], hours[-1] + pd.Timedelta("45min"), freq="15min")
    df = pd.DataFrame(index=idx)
    df["ac_power_kw"] = np.repeat(list(actual), 4)
    df["expected_kw"] = np.repeat(list(expected), 4)
    if clearsky is not None:
        df["clearsky_kw"] = np.repeat(list(clearsky), 4)
    if temp is not None:
        df["temp_c"] = np.repeat(list(temp), 4).astype(float)
    return df


CHOP_SITE = SimpleNamespace(dc_capacity_kw=2.0)


def test_csr_measures_sun_vs_clear_ceiling():
    day = make_intraday([0.5] * 8, [1.0] * 8, clearsky=[1.0] * 8)
    assert abs(day_csr(day) - 0.5) < 0.01


def test_csr_nan_without_clearsky_column():
    day = make_intraday([0.5] * 8, [1.0] * 8)
    assert pd.isna(day_csr(day))


def test_chop_high_on_broken_sky():
    # ratio alternates 0.9/0.4 hour to hour — sawtooth
    actual = [0.9, 0.4, 0.9, 0.4, 0.9, 0.4, 0.9, 0.4]
    day = make_intraday(actual, [1.0] * 8)
    assert chop_mad(day, CHOP_SITE) > 0.10


def test_chop_low_on_smooth_derate():
    # uniform 60% output: a fault scales smoothly
    day = make_intraday([0.6] * 8, [1.0] * 8)
    assert chop_mad(day, CHOP_SITE) < 0.10


def make_daily_with_rain(n, rain=0.0):
    daily = make_daily([1.0] * n)
    daily["rain_mm"] = rain
    return daily


WEATHER_SITE = SimpleNamespace(dc_capacity_kw=2.0)


def test_weather_fires_on_broken_sky():
    actual = [0.9, 0.4, 0.9, 0.4, 0.9, 0.4, 0.9, 0.4]
    day = make_intraday(actual, [1.0] * 8, clearsky=[1.3] * 8)  # csr ~0.5
    daily = make_daily_with_rain(1)
    assert detect_weather(daily.index[0], day, daily, WEATHER_SITE) is not None


def test_weather_rejects_smooth_derate():
    day = make_intraday([0.6] * 8, [1.0] * 8, clearsky=[1.3] * 8)
    daily = make_daily_with_rain(1)
    assert detect_weather(daily.index[0], day, daily, WEATHER_SITE) is None


def test_weather_rejects_bright_day():
    # underperforming but the sun was there: fault story, not weather
    actual = [0.9, 0.6, 0.9, 0.6, 0.9, 0.6, 0.9, 0.6]
    day = make_intraday(actual, [1.0] * 8, clearsky=[0.85] * 8)  # csr ~0.88
    daily = make_daily_with_rain(1)
    assert detect_weather(daily.index[0], day, daily, WEATHER_SITE) is None


def test_weather_dark_rain_path_needs_no_chop():
    day = make_intraday([0.2] * 8, [0.9] * 8, clearsky=[1.4] * 8)  # csr ~0.14, smooth
    daily = make_daily_with_rain(1, rain=4.2)
    evidence = detect_weather(daily.index[0], day, daily, WEATHER_SITE)
    assert evidence is not None and "rain" in evidence


def test_weather_inert_without_clearsky():
    day = make_intraday([0.4] * 8, [1.0] * 8)  # sensor site: no clearsky column
    daily = make_daily_with_rain(1, rain=4.2)
    assert detect_weather(daily.index[0], day, daily, WEATHER_SITE) is None


def test_unit_deficit_lands_on_step():
    site = SimpleNamespace(ac_capacity_kw=705.0, n_units=24)
    units, dist = unit_deficit(3 * 705.0 / 24, site)  # exactly 3 inverters
    assert abs(units - 3.0) < 0.01 and dist < 0.01


def test_unit_deficit_between_steps():
    site = SimpleNamespace(ac_capacity_kw=705.0, n_units=24)
    units, dist = unit_deficit(2.4 * 705.0 / 24, site)
    assert dist > 0.15  # fleet-uniform sag: lands between steps


THERMAL_SITE = SimpleNamespace(dc_capacity_kw=2.0, ac_capacity_kw=1.9, n_units=1)


def hot_sag_day(temps=(22, 25, 28, 31, 34, 36, 37, 35), depth=0.25):
    # ratio sags with the afternoon temp curve; temp peaks ~15:00
    ratio = [1.0 - depth * (t - 22) / 15 for t in temps]
    return make_intraday(
        [r * 1.0 for r in ratio], [1.0] * len(temps),
        clearsky=[1.05] * len(temps), temp=list(temps),
    )


def test_thermal_fires_on_hot_tracking_sag():
    day = hot_sag_day()
    daily = make_daily([1.0])
    assert detect_thermal(daily.index[0], day, daily, THERMAL_SITE) is not None


def test_thermal_rejects_cool_day():
    day = hot_sag_day()
    day["temp_c"] = day["temp_c"] - 15  # same shape, tmax ~22 C
    daily = make_daily([1.0])
    assert detect_thermal(daily.index[0], day, daily, THERMAL_SITE) is None


def test_thermal_rejects_quantized_deficit():
    # temps chosen so the bright-hours median deficit lands on exactly one
    # unit of a 4-unit site (0.5 kW): capacity loss, not heat — must yield
    site = SimpleNamespace(dc_capacity_kw=2.0, ac_capacity_kw=2.0, n_units=4)
    day = hot_sag_day(temps=(22, 28, 34, 37, 37, 37, 37, 36), depth=0.5)
    daily = make_daily([1.0])
    assert detect_thermal(daily.index[0], day, daily, site) is None


def test_thermal_rejects_without_temp_column():
    day = make_intraday([0.7] * 8, [1.0] * 8, clearsky=[1.05] * 8)
    daily = make_daily([1.0])
    assert detect_thermal(daily.index[0], day, daily, THERMAL_SITE) is None


def make_result(labels, start="2025-11-01"):
    idx = pd.date_range(start, periods=len(labels), freq="1D", tz="UTC")
    r = pd.DataFrame({"label": labels, "pi": 0.1, "evidence": "e"}, index=idx)
    r.index.name = "date"
    return r[r["label"].notna()]


def make_events_daily(n, start="2025-11-01"):
    idx = pd.date_range(start, periods=n, freq="1D", tz="UTC")
    return pd.DataFrame(
        {"actual_kwh": 1.0, "expected_kwh": 5.0, "coverage": 1.0}, index=idx
    )


EV_SITE = SimpleNamespace(coverage_min=0.8)


def test_events_merges_consecutive_same_label():
    r = make_result(["outage"] * 3)
    ev = events(r, make_events_daily(3), EV_SITE)
    assert len(ev) == 1
    assert ev.iloc[0]["days"] == 3
    assert abs(ev.iloc[0]["energy_deficit_kwh"] - 12.0) < 1e-9  # 3 * (5-1)


def test_events_split_by_healthy_day():
    r = make_result(["outage", None, "outage"])  # healthy middle day: no row
    ev = events(r, make_events_daily(3), EV_SITE)
    assert len(ev) == 2


def test_events_bridge_data_gap():
    r = make_result(["outage", "data_gap", "outage"])
    daily = make_events_daily(3)
    daily.iloc[1, daily.columns.get_loc("coverage")] = 0.4
    ev = events(r, daily, EV_SITE)
    assert len(ev) == 1
    assert ev.iloc[0]["label"] == "outage" and ev.iloc[0]["days"] == 3
    # gap day's half-seen actuals don't pollute the deficit
    assert abs(ev.iloc[0]["energy_deficit_kwh"] - 8.0) < 1e-9  # 2 valid days


def test_lone_data_gap_is_its_own_event():
    r = make_result(["data_gap"])
    ev = events(r, make_events_daily(1), EV_SITE)
    assert len(ev) == 1 and ev.iloc[0]["label"] == "data_gap"


def test_weather_inert_on_measured_poa_site():
    # sensor site: clouds cancel out of the ratio, chop there is hardware
    actual = [0.9, 0.4, 0.9, 0.4, 0.9, 0.4, 0.9, 0.4]
    day = make_intraday(actual, [1.0] * 8, clearsky=[1.3] * 8)
    day["poa_wm2"] = 800.0
    daily = make_daily_with_rain(1, rain=4.2)
    assert detect_weather(daily.index[0], day, daily, WEATHER_SITE) is None


def test_pi_step_labels_unclassified():
    from triage.classify import RULES, detect_pi_step

    label = next(lb for lb, fn in RULES if fn is detect_pi_step)
    assert label == Fault.UNCLASSIFIED
