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