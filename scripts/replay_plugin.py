"""Replay the cached SolarNetwork node 120 window through a running plugin
and diff its predictions against the batch pipeline's final labels.

The cache holds the canonical frame (UTC stamps on disk, kW, END-of-interval
labels); a node posts bucket-START stamps in watts — the shift and scale are
undone here, then datums stream chronologically one local day per /measure,
exactly as a SolarNode would deliver them. Batch truth comes from the latest
reports/sn120/sn120-*.csv export, no pipeline re-run needed.

Usage: uv run python scripts/replay_plugin.py [--url http://localhost:8000]
                                              [--chunk 1h]
The plugin should run with the node 120 site env and BACKFILL_DAYS=0 (a
historical replay must not mix in live fetches). --chunk sets how much
stream each /measure carries: production cadence is minutes, so the
default posts hourly batches (~4 datums each, ~5k requests) — mid-day
posts prove an in-progress day never closes early; --chunk 1D replays
fast at one post per day.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import httpx
import pandas as pd

CACHE = Path("data/sn120/node120_Solar_2025-08-01_2026-03-01.csv")
TZ = "Pacific/Auckland"
STEP = pd.Timedelta("15min")


def load_stream() -> pd.Series:
    df = pd.read_csv(CACHE, parse_dates=["measured_on"], index_col="measured_on")
    return df["ac_power_kw"].tz_convert(TZ).dropna()


def batch_labels() -> pd.Series:
    latest = sorted(Path("reports/sn120").glob("sn120-*.csv"))[-1]
    df = pd.read_csv(latest, parse_dates=["date"], index_col="date")
    return df["final_label"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--chunk", default="1h", help="stream per POST (e.g. 1h, 1D)")
    args = ap.parse_args()

    kw = load_stream()
    chunks = kw.groupby(pd.Grouper(freq=args.chunk))
    client = httpx.Client(base_url=args.url, timeout=120.0)

    health = client.get("/health")
    health.raise_for_status()
    print(f"plugin up: model {health.json()['details']['model_version']}, "
          f"replaying {len(kw)} intervals in {chunks.ngroups} {args.chunk} "
          f"posts from {CACHE.name}")

    predictions: dict[str, str] = {}
    unhealthy = 0
    for i, (_, series) in enumerate(sorted(chunks, key=lambda kv: kv[0])):
        if series.empty:
            continue
        datums = [
            {
                "nodeId": 120,
                "sourceId": "Solar",
                "timestamp": int((ts - STEP).timestamp()),
                "i": {"watts": float(v) * 1000.0},
            }
            for ts, v in series.items()
        ]
        r = client.post("/measure", json={"datums": datums})
        r.raise_for_status()
        body = r.json()
        if body["rejected"]:
            print(f"unexpected rejects: {body}", file=sys.stderr)
        for p in body["predictions"]:
            end = pd.Timestamp(p["timestamp"], unit="s", tz="UTC").tz_convert(TZ)
            predictions[str((end - STEP).date())] = p["s"]["faultClass"]
        if i % 100 == 0 and client.get("/health").status_code != 200:
            unhealthy += 1

    truth = batch_labels()
    rows = []
    for day, batch_label in truth.items():
        edge = predictions.get(str(day.date()))
        if edge is not None:
            rows.append((str(day.date()), batch_label, edge))
    frame = pd.DataFrame(rows, columns=["date", "batch", "edge"])

    agree = (frame["batch"] == frame["edge"]).mean()
    print(f"\n=== replay diff: {len(frame)} days scored, "
          f"{len(predictions)} predicted, agreement {agree:.3f}, "
          f"unhealthy health checks {unhealthy} ===\n")
    per_class = (
        frame.assign(match=frame["batch"] == frame["edge"])
        .groupby("batch")["match"]
        .agg(["count", "mean"])
        .rename(columns={"mean": "agreement"})
        .sort_values("count", ascending=False)
    )
    print(per_class.round(3).to_string())
    confusions = Counter(
        (b, e) for b, e in zip(frame["batch"], frame["edge"]) if b != e
    )
    if confusions:
        print("\ntop batch->edge confusions:")
        for (b, e), n in confusions.most_common(8):
            print(f"  {b} -> {e}: {n}")
    print(
        "\nExpected divergence sources: online healthy-median baseline vs the"
        "\nbatch two-pass fixpoint (pi_rel skew on flag-boundary days); days"
        "\nwhere the archive lacked POA and expected fell back to clear-sky;"
        "\nedge warmup (first days have no trailing history)."
    )


if __name__ == "__main__":
    main()
