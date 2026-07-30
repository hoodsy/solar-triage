import os

import pandas as pd

from triage.classify import classify
from triage.config import SITES
from triage.ingest import add_flags, build_daily, build_dataset
from triage.report import write_report


def main():
    # one process = one site: chosen at deploy time, e.g. TRIAGE_SITE=sn108
    site = SITES[os.environ.get("TRIAGE_SITE", "2107")]

    df = build_dataset(site)
    daily = build_daily(df, site).loc[site.report_start : site.report_end]
    daily = add_flags(daily, site)

    result = classify(daily, df, site)
    with pd.option_context("display.max_colwidth", None):
        print(result.to_string())

    write_report(result, daily, df, site)
    print("\nwrote reports/report.html")


if __name__ == "__main__":
    main()
