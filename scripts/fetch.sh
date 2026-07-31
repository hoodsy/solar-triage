#!/usr/bin/env bash
set -euo pipefail

# Fetch PVDAQ system 2107 (Farm Solar Array, Arbuckle CA)
# Public bucket, no AWS account needed. ~445 MB total.

BUCKET="s3://oedi-data-lake/pvdaq/2023-solar-data-prize/2107_OEDI"
DEST="data/2107"

mkdir -p "$DEST"

# See what's there first
aws s3 ls --no-sign-request --recursive --human-readable "$BUCKET/"

# Pull everything (sync = resumable, safe to re-run)
aws s3 sync --no-sign-request "$BUCKET/" "$DEST/"

# --- PVDAQ system 9069 (Simon Solar Farm, Social Circle GA) ---
# Same prize bucket. The full set is 23 GB of per-string DC channels;
# the pipeline only needs the four plant-level files + metadata (~2.2 GB).
B9="s3://oedi-data-lake/pvdaq/2023-solar-data-prize/9069_OEDI"
mkdir -p data/9069/data data/9069/metadata
for f in meter_data irradiance_data environment_data electrical_ac; do
  aws s3 cp --no-sign-request "$B9/data/9069_${f}.csv" data/9069/data/
done
aws s3 cp --no-sign-request --recursive "$B9/metadata/" data/9069/metadata/