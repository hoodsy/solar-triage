# Triage

Daily solar fault triage from a plant's power meter stream, trained on 33
public systems (NREL PVDAQ and SolarNetwork). The model and training data
are published on Hugging Face:
[hoodsy/sn-triage](https://huggingface.co/hoodsy/sn-triage) and
[hoodsy/sn-triage-dataset](https://huggingface.co/datasets/hoodsy/sn-triage-dataset).

## Overview

This plugin monitors a plant's AC power and issues one health assessment
per day. It compares each day's actual production against what the site
should have produced, computed from location, panel geometry, and weather
with no on-site irradiance sensor required, then classifies the day as
healthy or as a specific fault. Healthy days are reported too, so the
output doubles as a daily status feed and lets operators catch failing or
underperforming plants early.

### Labels

`healthy`, `outage`, `weather`, `snow`, `snow_shedding`,
`cloud_intermittent`, `clipping`, `curtailment`, `thermal`, plus
deterministic `data_gap`.

## Installation

```sh
docker run -p 8000:8000 -v triage-data:/data \
  --env-file site.env ghcr.io/hoodsy/triage-plugin:latest
```

```sh
site.env:

SITE_TZ=Pacific/Auckland
LAT=-36.85
LON=174.76
TILT=25
AZIMUTH=0
DC_KW=2.0
AC_KW=1.9
NODE_ID=120
POWER_SOURCE_ID=Solar
```

| Env                                        | Meaning                                                          |
| ------------------------------------------ | ---------------------------------------------------------------- |
| `SITE_TZ`, `LAT`, `LON`, `TILT`, `AZIMUTH` | site location and geometry (azimuth pvlib convention, 0 = north) |
| `DC_KW`, `AC_KW`                           | nameplate DC and empirical AC ceiling                            |
| `NODE_ID`, `POWER_SOURCE_ID`               | node and the AC-power source to ingest                           |
| `INTERVAL`                                 | datum cadence (default `15min`)                                  |
| `PREDICTION_SOURCE_ID`                     | source id for predictions (default `/triage/1`)                  |
| `BACKFILL_DAYS`                            | boot backfill window (default 30; 0 disables)                    |
| `WEATHER`                                  | Open-Meteo fetch (default true; false = clear-sky only)          |
| `DB_PATH`                                  | SQLite buffer (default `/data/triage.db`; mount a volume)        |

## API

`GET /health`: status, uptime, model version, closed-day and buffered-interval counts.

`POST /measure`: send datums; receive any newly closed days' predictions.

```json
{
  "datums": [
    {
      "nodeId": 120,
      "sourceId": "Solar",
      "timestamp": 1767219300,
      "i": { "watts": 1450.0 }
    }
  ]
}
```

```json
{
  "accepted": 1,
  "rejected": 0,
  "predictions": [
    {
      "nodeId": 120,
      "sourceId": "/triage/1",
      "timestamp": 1767222000,
      "s": { "faultClass": "outage" },
      "meta": {
        "confidence": 0.996,
        "history_days": 152,
        "model_version": "20260801T034437Z"
      }
    }
  ],
  "message": "stored 1 power intervals"
}
```

## Notes

- **Day close:** days are labeled on data time, not wall clock. A day
  closes once datums beyond it arrive (fully past in `SITE_TZ`);
  predictions return in the next `/measure` response. Replays work at
  any speed.
- **Data gaps:** days under the coverage threshold return a deterministic
  `data_gap`. The model is not consulted.
- **Backfill:** boot pulls the trailing `BACKFILL_DAYS` from the
  SolarNetwork API. A failed fetch (private node) is a logged warning,
  not a crash; the plugin cold-starts on `/measure` data alone. Set
  `BACKFILL_DAYS=0` to skip.
- **Warm-up:** the performance baseline needs 5 healthy closed days,
  trend features mature at ~14 days, the snow trail at 30. Until then
  the model judges on intraday shape alone.
- **History depth:** `meta.history_days` says how much history backed
  each prediction. Discount anything below 5.
- **Long outages:** when the trailing window has no healthy days, the
  last good baseline is held rather than recomputed from fault days.
- **Weather:** with `WEATHER=false` (or no egress), weather features are
  NaN and expected power falls back to clear-sky. The model tolerates
  missing values.
- **State:** one SQLite file. Mount `/data` to survive restarts;
  duplicate datums upsert, so re-sending is safe.

## Validation

Replaying 7 months of a real node (including a 77-day outage) through the
container reproduced the offline pipeline's labels on 92.4% of 211 days
(outage 88/88, weather 44/44). Offline, the model scores leave-one-site-out
macro-F1 0.92 across 33 sites. See `scripts/replay_plugin.py`.
