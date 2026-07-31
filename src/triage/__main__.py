import os

import pandas as pd

from triage.adapters.pvdaq import load_inverters
from triage.build import add_flags, build_daily, build_dataset
from triage.classify import classify, events
from triage.config import SITES
from triage.referee import daily_divergence, resolve
from triage.report import report
from triage.trend import daily_insolation, daily_pi, degradation, soiling


def main():
    # one process = one site: chosen at deploy time, e.g. TRIAGE_SITE=sn120
    site = SITES[os.environ.get("TRIAGE_SITE", "2107")]

    df, masked = build_dataset(site)
    daily_full = build_daily(df, site)
    daily = add_flags(daily_full.loc[site.report_start : site.report_end], site)
    result = classify(daily, df, site)

    # sub-metered sites: the per-inverter referee grades claims and
    # attributes the classifier's honest unclassified days
    if site.electrical:
        final = resolve(result, daily_divergence(load_inverters(site)), site, df)
    else:
        final = result

    ev = events(final, daily, site)
    pi_full = daily_pi(daily_full, site)
    trend_degradation = degradation(pi_full)
    trend_soiling = soiling(pi_full, daily_insolation(df, site))

    with pd.option_context("display.max_colwidth", None):
        if masked:
            print(
                "quality: masked "
                + "; ".join(f"{v} {k}" for k, v in masked.items())
            )
        if not ev.empty:
            print(ev.to_string(index=False), end="\n\n")
        print(final.to_string())
        counts = {str(k): v for k, v in final["label"].value_counts().items()}
        print("\nlabels:", counts)
        if "verdict" in final.columns:
            print("verdicts:", final["verdict"].value_counts().to_dict())
        print("degradation:", trend_degradation)
        print("soiling:", trend_soiling)

    report(
        final,
        ev,
        daily,
        df,
        site,
        masked=masked,
        degradation=trend_degradation,
        soiling=trend_soiling,
    )
    print("\nwrote reports/report.html")


if __name__ == "__main__":
    main()
