"""Train/test split harness: the exam design.

Two rules keep evaluation honest. A multi-day event is ONE example —
day 41 of an outage in train and day 42 in test is showing the model the
answer — so random splits happen at event granularity (consecutive
same-label days at one site share an event id). And the question that
matters is "does this work on a plant it has never seen?", so the
headline protocol is leave-one-site-out: train on every other site,
predict the held-out one, rotate.

Splits are deterministic (hash of the event id), so two people running
the same data get the same folds without storing any state.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path

import pandas as pd


def load_training(reports_dir: str | Path = "reports") -> pd.DataFrame:
    """Concatenate the LATEST training CSV of every site. Timestamped
    names sort lexicographically, so [-1] per directory is the newest."""
    frames = []
    for site_dir in sorted(Path(reports_dir).iterdir()):
        csvs = sorted(site_dir.glob(f"{site_dir.name}-*.csv"))
        if csvs:
            frames.append(pd.read_csv(csvs[-1], parse_dates=["date"]))
    out = pd.concat(frames, ignore_index=True)
    out["site"] = out["site"].astype(str)
    return out


def assign_events(df: pd.DataFrame) -> pd.Series:
    """Event id per row: consecutive same-label days at one site share one.
    A gap or a label change starts a new event; healthy runs are events
    too (a fair test set needs unseen healthy stretches, not cherry-picked
    single days)."""
    df = df.sort_values(["site", "date"])
    new = (
        (df["site"] != df["site"].shift())
        | (df["final_label"] != df["final_label"].shift())
        | (df["date"].diff().dt.days != 1)
    )
    ids = (
        df["site"]
        + ":"
        + df["final_label"].astype(str)
        + ":"
        + new.cumsum().astype(str)
    )
    return ids.reindex(df.index).rename("event_id")


def _bucket(event_id: str, salt: str = "") -> float:
    """Stable [0, 1) hash of an event id — the deterministic coin flip."""
    h = hashlib.sha256((salt + event_id).encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64


def event_split(
    df: pd.DataFrame, test_frac: float = 0.2, salt: str = ""
) -> pd.Series:
    """Boolean test-set mask, split at event granularity: every day of an
    event lands on the same side. `salt` varies the fold."""
    events = assign_events(df)
    return events.map(lambda e: _bucket(e, salt) < test_frac).rename("is_test")


def leave_one_site_out(
    df: pd.DataFrame,
) -> Iterator[tuple[str, pd.Series]]:
    """Yield (held_out_site, test_mask) per site — train on the rest.
    The headline metric: a model that only memorized its training plants
    scores near chance here."""
    for site in sorted(df["site"].unique()):
        yield site, (df["site"] == site).rename("is_test")
