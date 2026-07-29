import pandas as pd

from triage.classify import classify
from triage.ingest import add_flags, build_daily, build_dataset
from triage.report import write_report


def main():
    df = build_dataset()
    daily = build_daily(df).loc["2024-01-01":"2024-11-30"]
    daily = add_flags(daily)

    result = classify(daily, df)
    with pd.option_context("display.max_colwidth", None):
        print(result.to_string())

    write_report(result, daily, df)
    print("\nwrote reports/report.html")


if __name__ == "__main__":
    main()
