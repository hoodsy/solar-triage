# Solar PV fault triage

Daily fault triage for solar plants, built on public data (PVDAQ,
SolarNetwork). Per site: flag underperforming days against a rolling
baseline, classify them with evidence-backed rules, grade the claims
against per-inverter data where it exists, and distill every day into a
training set for a student model that works on plants it has never seen.

## Layout

```
src/triage/
  config.py   per-site SiteConfig dataclass (declarations only)
  ingest/     raw data -> canonical frame: source adapters (PVDAQ files,
              PVDAQ parquet lake, SolarNetwork), Open-Meteo weather POA,
              pvanalytics quality gate, physics models, frame assembly
              (build.py), and sites/ — one config module per site
  classify/   rule classifier (__init__.py), per-inverter referee,
              RdTools degradation/soiling trends, HTML report + plots
  train/      per-day feature vectors, event/LOSO split harness,
              training-set export, gradient-boosted student (model.py)
scripts/      fetch.sh + fetch_lake.sh (PVDAQ downloads, public S3),
              convert_lake_csv.py (CSV-only lake -> parquet)
reports/      per-site report.html + exported training CSVs (gitignored)
model/        trained model.joblib (gitignored)
```

## Work so far

- **31 sites onboarded.** The two Solar Data Prize plants (2107 "Farm
  Solar Array", 893 kW; 9069 "Simon Solar Farm", 38.7 MW), a residential
  SolarNetwork node (sn120, no irradiance sensor, real 77-day outage),
  and 28 PVDAQ systems across desert/snow/coastal/SoCal climates —
  a deliberate clipping site (1278, DC/AC 1.24), a CAISO curtailment
  trio (14597/14601/14645), and the 29-year NREL x-Si twins (50/51).
  Onboarding is config-only: one module in `ingest/sites/`.
- **Rules + referee.** Quality gate -> daily-PI flagging -> rule labels;
  on sub-metered sites a fleet-relative referee grades each claim
  (confirmed/refuted/attributed) and resolves honest unclassified days.
  Referee-graded days are the gold label tier.
- **Training set.** 89k site-days exported with feature vectors, rule
  label, final label, and provenance; identical schema across sites.
  66k trainable (9 classes), 5.9k referee-graded gold.
- **Student model.** Gradient-boosted trees over the per-day features,
  sample-weighted by provenance (gold x5) and class balance.
  Leave-one-site-out macro-F1 0.92 — curtailment is the hard class
  (0.68). On the 1,449 days where the referee overruled the rules, the
  student (never trained on the site) sides with the referee 77% of the
  time and with the old rule label 0%.

## Running

```
scripts/fetch.sh                           # one-time PVDAQ download
uv run --env-file .env python -m triage    # pipeline for this device's site
uv run python -m triage.train              # train + evaluate the student
```

One process serves one site, chosen by `TRIAGE_SITE` (keys of `SITES` in
`ingest/sites/`; copy `.env.example` to `.env`). The pipeline prints the
label/verdict tables and writes `reports/<site>/report.html` plus the
training CSV; training reads those CSVs and writes `model/model.joblib`.

Onboarding a site: add a module under `ingest/sites/` with a `SiteConfig`
named `SITE`, register it in `ingest/sites/__init__.py`. Sites without an
irradiance stream get expected power from Open-Meteo reanalysis or the
pvlib clear-sky ceiling. Read `data/<site>/metadata/` before guessing
geometry — and verify it against the data (2107's as-built azimuth is
13° off its paperwork).
