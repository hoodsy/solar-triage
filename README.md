# solar-triage

[![Model on HF](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Model-yellow)](https://huggingface.co/hoodsy/sn-triage)
[![Dataset on HF](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Dataset-yellow)](https://huggingface.co/datasets/hoodsy/sn-triage-dataset)
[![Edge image](https://img.shields.io/badge/GHCR-triage--plugin-blue)](https://github.com/hoodsy/solar-triage/pkgs/container/triage-plugin)

Daily fault triage for solar PV plants, trained on public data.
Rules flag and label each plant-day, a per-inverter referee grades the
rules where sub-metering exists, and a gradient-boosted student distills
it all — built to work on plants it has never seen.

Nine labels: `healthy` `outage` `weather` `snow` `snow_shedding`
`cloud_intermittent` `clipping` `curtailment` `thermal`

## Results

| Protocol | Score |
|---|---|
| Leave-one-site-out macro-F1, 33 sites | **0.92** |
| Held-out pair vs frozen model, 1,710 days | 0.984 agreement |
| — referee-graded slice, 208 gold days | 0.885 |
| Edge replay, containerized, 211 days (incl. a 77-day outage) | 0.924 |
| Referee-overruled days: student sides with referee / old label | 77% / 0% |

## Quick start

```sh
scripts/fetch.sh                           # one-time PVDAQ download
uv run --env-file .env python -m triage    # run one site (TRIAGE_SITE)
uv run python -m triage.train              # train + evaluate the student
```

Edge plugin (SolarQuant spec — `POST /measure` in, prediction datums out):

```sh
docker pull ghcr.io/hoodsy/triage-plugin:latest
docker run -p 8000:8000 -v triage-data:/data \
  -e SITE_TZ=... -e LAT=... -e LON=... -e TILT=... -e AZIMUTH=... \
  -e DC_KW=... -e AC_KW=... -e NODE_ID=... -e POWER_SOURCE_ID=... \
  ghcr.io/hoodsy/triage-plugin
uv run python scripts/replay_plugin.py     # replay a real window, diff vs batch
```

## How it works

- **Pipeline** (per site): quality gate → expected power (POA sensor →
  Open-Meteo reanalysis → clear-sky ladder) → rolling-baseline flagging →
  rule classifier → per-inverter referee → report + per-day export.
- **Training**: 91k site-days across 33 systems (2 kW roof → 38.7 MW farm);
  68k trainable, 6.1k referee-graded gold weighted 5×.
- **Edge** (`src/triage/plugin/`): the model alone in a 968 MB container —
  SQLite datum buffer, local day-close, same features, 30-day boot
  backfill. `data_gap` is answered deterministically, never guessed.

## Layout

```
src/triage/
  config.py   per-site SiteConfig (declarations only)
  ingest/     adapters, weather, quality gate, physics, day build, sites/
  classify/   rule classifier, referee, trends, HTML report
  train/      features, event/LOSO splits, export, student model
  plugin/     SolarQuant edge plugin
scripts/      data fetchers + plugin replay harness
```

Onboarding a site is config-only: one module in `ingest/sites/` — but
verify metadata against the data first (one site's as-built azimuth was
13° off its paperwork). Field names in prediction datums are provisional
pending Ecosuite and isolated in `plugin/constants.py`.

Data: NREL [PVDAQ](https://data.openei.org/submissions/4568) (CC BY 4.0),
[Open-Meteo](https://open-meteo.com/)/ERA5 (CC BY 4.0),
[SolarNetwork](https://solarnetwork.net/). MIT licensed.
