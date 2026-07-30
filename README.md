# Overview

Data from [PVDAQ](https://github.com/openEDI/documentation/blob/main/pvdaq.md#-5-mw-dc-system-ids) prize dataset for `2107`, "A 893 kW Fixed ground-mount facility in a highly active agricultural area in California".

# Data

Run `/scripts/fetch.sh` to download the dataset

# Running

```
uv run --env-file .env python -m triage.main    # site from this device's .env
TRIAGE_SITE=sn108 uv run python -m triage.main  # or set the env var directly
```

One process serves one site, chosen by the `TRIAGE_SITE` env var (keys of
`SITES` in `triage/config.py`). Each deployed device carries its own `.env`
(copy `.env.example`; gitignored) and uv's `--env-file` loads it — the code
itself only ever reads the environment. Output: classification table on
stdout and `reports/report.html`.

Onboarding a site is config-only: add a `SiteConfig` entry with either a
`CsvAdapter` (declarative file specs: per-file timestamp column/timezone,
dedupe precedence, native resolution) or a `SolarNetworkAdapter` (node +
source ID, trailing-window fetch). Sites without an irradiance stream get
expected power from a pvlib clear-sky model — a ceiling, not a forecast, so
their PI is weather-noisy and flag thresholds need per-site tuning (sn108
ships untuned; its labels are demo-quality).
