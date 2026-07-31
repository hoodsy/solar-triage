"""Convert CSV-lake-only systems (PVDB cohort) to the long-parquet layout
PvdaqLakeAdapter reads.

The parquet mirror froze in 2022; newer systems exist only as yearly wide
CSVs (14601_ac_2016..._corrected.csv) whose columns carry device names,
not __NNNN metric-id suffixes. This melts them to (measured_on,
metric_id, value) under data/<id>/lake/year=YYYY/, assigning ids by
enumerating the sorted union of column names — recorded in
data/<id>/lake_manifest.json so configs can cite ids by name. Prefers
*_corrected.csv; the uncorrected duplicates of the same span are skipped.

Usage: uv run python scripts/convert_lake_csv.py <system_id>
"""

import json
import sys
from pathlib import Path

import pandas as pd

SENTINELS = [-1000000.0, -999.0, -9999.0]


def main(sid: str) -> None:
    src = Path(f"data/{sid}/csvsrc")
    dest = Path(f"data/{sid}/lake")
    files = sorted(src.rglob("*_corrected.csv"))
    plain = [
        p for p in sorted(src.rglob("*.csv"))
        if "corrected" not in p.name
        and not any(p.name.replace(".csv", "") in c.name for c in files)
    ]
    files += plain
    columns: set[str] = set()
    for p in files:
        columns |= set(pd.read_csv(p, nrows=0).columns) - {"measured_on"}
    manifest = {name: i + 1 for i, name in enumerate(sorted(columns))}
    Path(f"data/{sid}/lake_manifest.json").write_text(json.dumps(manifest, indent=1))

    for p in files:
        df = pd.read_csv(p, parse_dates=["measured_on"], na_values=SENTINELS)
        long = df.melt("measured_on", var_name="name", value_name="value").dropna(
            subset=["value"]
        )
        long["metric_id"] = long["name"].map(manifest).astype("int32")
        long = long[["measured_on", "metric_id", "value"]]
        for year, g in long.groupby(long["measured_on"].dt.year):
            out = dest / f"year={year}"
            out.mkdir(parents=True, exist_ok=True)
            g.to_parquet(out / f"{p.stem}.parquet", index=False)
        print(f"{p.name}: {len(long)} rows")
    print(f"manifest: {len(manifest)} channels")


if __name__ == "__main__":
    main(sys.argv[1])
