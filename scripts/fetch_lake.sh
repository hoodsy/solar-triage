#!/usr/bin/env bash
set -euo pipefail

# Fetch one main-lake PVDAQ system from the parquet mirror (public bucket,
# no AWS account). Usage: fetch_lake.sh <system_id> [first_year] [last_year]
# Lands in data/<system_id>/lake/year=YYYY/... plus the metadata JSON.

id="$1"; first="${2:-0}"; last="${3:-9999}"
dest="data/$id/lake"
mkdir -p "$dest" "data/$id/metadata"

aws s3 cp --no-sign-request \
  "s3://oedi-data-lake/pvdaq/csv/system_metadata/${id}_system_metadata.json" \
  "data/$id/metadata/" 2>/dev/null || echo "note: no metadata JSON for $id"

years=$(aws s3 ls --no-sign-request \
  "s3://oedi-data-lake/pvdaq/parquet/pvdata/system_id=${id}/" \
  | sed -n 's/.*year=\([0-9]*\).*/\1/p')
for y in $years; do
  if [ "$y" -ge "$first" ] && [ "$y" -le "$last" ]; then
    echo "$id: year $y"
    # sync, not cp: fetches are long and restartable syncs make retries cheap
    aws s3 sync --no-sign-request --quiet \
      "s3://oedi-data-lake/pvdaq/parquet/pvdata/system_id=${id}/year=${y}/" \
      "$dest/year=${y}/"
  fi
done
