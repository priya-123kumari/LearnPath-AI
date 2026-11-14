#!/usr/bin/env bash
# Step 10: regenerate twice with the same seed and compare row counts + SHA-256 checksums of every output file,
# and compare against the published dataset's checksums.json.
# Usage: ./reproducibility_check.sh [scale] [seed]        e.g. ./reproducibility_check.sh starter 20261022
set -euo pipefail
SCALE="${1:-starter}"; SEED="${2:-20261022}"
PY="${PYTHON:-python}"
$PY -m database.generator.reproduce --scale "$SCALE" --seed "$SEED" --against "database/data/$SCALE"
