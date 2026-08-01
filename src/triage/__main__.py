import os

import pandas as pd

from triage.ingest.build import add_flags, build_daily, build_dataset
from triage.classify import classify, events
from triage.train.export import export_training
from triage.ingest.sites import SITES
from triage.classify.referee import daily_divergence, resolve
from triage.classify.report import report
from triage.classify.trend import daily_insolation, daily_pi, degradation, soiling


def main():
    # one process = one site: chosen at deploy time, e.g. TRIAGE_SITE=sn120
    key = os.environ.get("TRIAGE_SITE", "2107")
    site = SITES[key]

    df, masked = build_dataset(site)
    daily_full = build_daily(df, site)
    daily = add_flags(daily_full.loc[site.report_start : site.report_end], site)
    result = classify(daily, df, site)

    # sub-metered sites: the per-inverter referee grades claims and
    # attributes the classifier's honest unclassified days
    if site.electrical:
        final = resolve(
            result, daily_divergence(site.source.load_inverters(site)), site, df
        )
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

    csv_path = export_training(daily, result, final, key, df, site)
    report(
        final,
        ev,
        daily,
        df,
        site,
        masked=masked,
        degradation=trend_degradation,
        soiling=trend_soiling,
        path=f"reports/{key}/report.html",
    )
    print(f"\nwrote reports/{key}/report.html and {csv_path}")


if __name__ == "__main__":
    main()
