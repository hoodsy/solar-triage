# Overview

Solar PV fault triage across public datasets: flag underperforming days
against a rolling baseline, classify them with evidence-backed rules, grade
and attribute the claims against per-inverter data where it exists, and
measure the slow trends the daily rules are blind to.

Sites onboarded:

- `2107` — [PVDAQ](https://github.com/openEDI/documentation/blob/main/pvdaq.md)
  Solar Data Prize, "Farm Solar Array": 893 kW fixed ground mount, Arbuckle CA.
  Measured POA + ambient temp + 24 sub-metered inverters.
- `9069` — PVDAQ Solar Data Prize, "Simon Solar Farm": 38.7 MW utility site,
  Social Circle GA. 40 sub-metered inverters; a data-quality obstacle course
  (frozen reference cells, two disjoint meter eras).
- `sn120` — SolarNetwork public node 120: ~2 kW residential, Auckland NZ.
  No irradiance sensor — expected power comes from Open-Meteo reanalysis;
  the study window spans a real 77-day outage.

# Data

Run `scripts/fetch.sh` to download the PVDAQ files (public S3, no account).
SolarNetwork and Open-Meteo data are fetched and cached on first run.

# Running

```
uv run --env-file .env python -m triage    # site from this device's .env
TRIAGE_SITE=sn120 uv run triage            # or set the env var directly
```

One process serves one site, chosen by the `TRIAGE_SITE` env var (keys of
`SITES` in `triage/config.py`). Each deployed device carries its own `.env`
(copy `.env.example`; gitignored) and uv's `--env-file` loads it — the code
itself only ever reads the environment.

The single command runs the whole pipeline: quality gate (pvanalytics) →
daily PI flagging → rule classifier → referee attribution on sub-metered
sites (per-inverter fleet grading: confirms/refutes claims, attributes
unclassified days) → event aggregation → RdTools degradation + soiling.
Output: summary tables on stdout and `reports/report.html` with season
energy, PI/flags, data quality, events, final labels, referee verdicts,
slow trends, and per-day evidence charts.

Onboarding a site is config-only: add a `SiteConfig` entry with either a
`PvdaqAdapter` (declarative file specs: per-file timestamp column/timezone,
dedupe precedence, native resolution, optional temperature stream) or a
`SolarNetworkAdapter` (node + source ID, fixed or trailing window). Sites
without an irradiance stream get expected power from Open-Meteo reanalysis
or the pvlib clear-sky ceiling — weather-noisy PI, so flag thresholds need
per-site tuning. Read `data/<site>/metadata/` before guessing geometry —
and verify it against the data (2107's as-built azimuth is 13° off its
paperwork: magnetic south).
