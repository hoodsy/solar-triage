"""SQLite state: the interval buffer, closed days, and the prediction queue.

The DB is the plugin's only durable state — datums survive restarts, closed
days are never recomputed, and queued predictions outlive the response that
should have carried them. Endpoints are async-def and never await, so
handlers serialize on the event loop and one connection needs no locking.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS intervals (
  source_id TEXT NOT NULL,
  ts        INTEGER NOT NULL,  -- unix seconds, UTC, as posted by the node
  watts     REAL,
  PRIMARY KEY (source_id, ts)
);
CREATE TABLE IF NOT EXISTS days (
  date         TEXT PRIMARY KEY,  -- local date in SITE_TZ, ISO
  actual_kwh   REAL,
  expected_kwh REAL,
  coverage     REAL,
  pi           REAL,
  pi_baseline  REAL,
  rain_mm      REAL,
  snow_cm      REAL,
  label        TEXT NOT NULL,
  confidence   REAL,
  closed_at    INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS predictions (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  payload   TEXT NOT NULL,  -- the spec Prediction object, JSON
  delivered INTEGER NOT NULL DEFAULT 0
);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def buffered_intervals(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM intervals").fetchone()[0]


def closed_days(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM days").fetchone()[0]


def upsert_intervals(
    conn: sqlite3.Connection, rows: Iterable[tuple[str, int, float]]
) -> None:
    """(source_id, unix ts, watts) rows; a repeated timestamp replaces, so
    re-posted datums and backfill overlaps never double-count."""
    conn.executemany(
        "INSERT OR REPLACE INTO intervals (source_id, ts, watts) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()


def queue_prediction(conn: sqlite3.Connection, payload: dict) -> None:
    conn.execute("INSERT INTO predictions (payload) VALUES (?)", (json.dumps(payload),))
    conn.commit()


def drain_predictions(conn: sqlite3.Connection) -> list[dict]:
    """Undelivered predictions, oldest first; marks them delivered."""
    rows = conn.execute(
        "SELECT id, payload FROM predictions WHERE delivered = 0 ORDER BY id"
    ).fetchall()
    if rows:
        conn.executemany(
            "UPDATE predictions SET delivered = 1 WHERE id = ?",
            [(row_id,) for row_id, _ in rows],
        )
        conn.commit()
    return [json.loads(payload) for _, payload in rows]
