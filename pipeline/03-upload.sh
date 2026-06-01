#!/usr/bin/env bash
# Upload do pmtiles versionado pro R2 com Cache-Control immutable.
set -euo pipefail

: "${WEEK:?WEEK env required}"
: "${PMTILES_NAME:?PMTILES_NAME env required}"
: "${R2_BUCKET:?R2_BUCKET env required}"

WORKDIR="${WORKDIR:-/work}"
cd "$WORKDIR"

if [[ ! -f "$PMTILES_NAME" ]]; then
    echo "[03] ERROR: $PMTILES_NAME not found in $WORKDIR" >&2
    exit 2
fi

echo "[03] Uploading $PMTILES_NAME → r2://$R2_BUCKET/ ..."

rclone copy "$PMTILES_NAME" "alfaero:$R2_BUCKET/" \
    --progress \
    --transfers 8 \
    --checkers 16 \
    --s3-chunk-size 64M \
    --s3-upload-concurrency 8 \
    --header-upload "Cache-Control: public, max-age=31536000, immutable" \
    --header-upload "Content-Type: application/octet-stream"

# Confirma presença
if ! rclone lsf "alfaero:$R2_BUCKET/$PMTILES_NAME" >/dev/null; then
    echo "[03] ERROR: upload verification failed" >&2
    exit 3
fi

echo "[03] Uploaded $PMTILES_NAME to r2://$R2_BUCKET/"
