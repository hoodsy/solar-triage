import os
import pandas as pd

from triage.build import build
from triage.classify import classify, events
from triage.config import SITES
from triage.report import report


def main():
    # one process = one site: chosen at deploy time, e.g. TRIAGE_SITE=sn108
    site = SITES[os.environ.get("TRIAGE_SITE", "2107")]

    df, daily = build(site)
    result = classify(daily, df, site)

    with pd.option_context("display.max_colwidth", None):
        ev = events(result, daily, site)
        if not ev.empty:
            print(ev.to_string(index=False), end="\n\n")
        print(result.to_string())
    report(result, daily, df, site)
    print("\nwrote reports/report.html")


if __name__ == "__main__":
    main()
