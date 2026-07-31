from types import SimpleNamespace

import pandas as pd

from triage.report import report

SITE = SimpleNamespace(
    name="Test Site",
    ac_capacity_kw=10.0,
    flag_threshold=0.92,
    window=30,
    coverage_min=0.8,
)


def make_frames(labels, verdicts=None):
    days = pd.date_range("2024-06-01", periods=5, freq="1D", tz="UTC")
    daily = pd.DataFrame(
        {
            "actual_kwh": 40.0,
            "expected_kwh": 50.0,
            "coverage": 1.0,
            "pi": 0.8,
            "pi_baseline": 1.0,
            "flagged": True,
        },
        index=days.rename("measured_on"),
    )
    idx = pd.date_range("2024-06-01", periods=5 * 96, freq="15min", tz="UTC")
    df = pd.DataFrame({"ac_power_kw": 5.0, "expected_kw": 6.0}, index=idx)
    final = pd.DataFrame(
        {"label": labels, "pi": 0.8, "evidence": "because"},
        index=days[: len(labels)].rename("date"),
    )
    if verdicts is not None:
        final["verdict"] = verdicts
    ev = pd.DataFrame(
        {"label": [labels[0]], "start": [days[0].date()], "end": [days[-1].date()],
         "days": [5], "median_pi": [0.8], "energy_deficit_kwh": [50.0],
         "evidence": ["because"]}
    )
    return final, ev, daily, df


def render(tmp_path, verdicts=None):
    final, ev, daily, df = make_frames(["outage"] * 3, verdicts)
    path = tmp_path / "r.html"
    report(
        final, ev, daily, df, SITE,
        masked={"meter stale": 4},
        degradation="+0.10 %/yr",
        soiling="n/a — needs measured POA",
        path=str(path),
    )
    return path.read_text()


def test_report_sections_render(tmp_path):
    html = render(tmp_path)
    for heading in ("Season energy", "Data quality", "Events", "Final labels",
                    "Slow trends"):
        assert heading in html
    assert "meter stale" in html
    assert "+0.10 %/yr" in html
    # precedence text derived from RULES, never hand-written
    assert "data_gap &gt; outage &gt; thermal" in html
    assert "classifier only" in html.lower()
    assert "Verdicts on classifier claims" not in html


def test_report_verdicts_section_when_graded(tmp_path):
    html = render(tmp_path, verdicts=["confirmed", "refuted", "attributed"])
    assert "Verdicts on classifier claims" in html
    assert "refuted days:" in html
    assert "per-inverter attribution" in html
    assert "referee: confirmed" in html
