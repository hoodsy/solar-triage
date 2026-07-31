#!/usr/bin/env bash
set -euo pipefail

# Fetch the PVDAQ Solar Data Prize files the pipeline actually reads.
# Public bucket, no AWS account needed.

PRIZE="s3://oedi-data-lake/pvdaq/2023-solar-data-prize"

# --- 2107 (Farm Solar Array, Arbuckle CA) ---
mkdir -p data/2107/data data/2107/metadata
for f in \
  2107_meter_15m_data.csv 2107_meter_15m_data_2024.csv 2107_meter_15m_data_2025.csv \
  2107_irradiance_data.csv 2107_irradiance_data_2024.csv 2107_irradiance_15m_data_2025.csv \
  2107_environment_data.csv 2107_environment_data_2024.csv \
  2107_electrical_data.csv 2107_electrical_data_2024.csv 2107_electrical_data_2025.csv
do
  aws s3 cp --no-sign-request "$PRIZE/2107_OEDI/data/$f" data/2107/data/
done
aws s3 cp --no-sign-request --recursive "$PRIZE/2107_OEDI/metadata/" data/2107/metadata/

# --- 9069 (Simon Solar Farm, Social Circle GA) ---
# The full set is 23 GB of per-string DC channels; the pipeline needs four
# plant-level files (~2.2 GB) + metadata.
mkdir -p data/9069/data data/9069/metadata
for f in meter_data irradiance_data environment_data electrical_ac; do
  aws s3 cp --no-sign-request "$PRIZE/9069_OEDI/data/9069_${f}.csv" data/9069/data/
done
aws s3 cp --no-sign-request --recursive "$PRIZE/9069_OEDI/metadata/" data/9069/metadata/
